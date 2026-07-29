# 비트별장 회차의 날짜 기반 전이(생성·마감·통보)를 처리하는 스케줄러 작업
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from . import models, villa_notify
from .database import SessionLocal
from .routers import villa as villa_router

logger = logging.getLogger(__name__)

# 접수 마감 며칠 전에 관리자에게 리마인더를 보낼지
REMINDER_DAYS_BEFORE = 3


def _pending_count(db: Session, round_id: int) -> int:
    return db.query(models.VillaReservation).filter(
        models.VillaReservation.round_id == round_id,
        models.VillaReservation.status == "applied",
    ).count()


def ensure_current_round(db: Session, today):
    """
    현재 대상월과 그 직전 달(선착순 오픈 대상) 회차를 미리 만들어 둔다. get_or_create이므로 멱등하다.
    직전 달 회차까지 함께 보장해 두어야, 서버가 한 달가량 멈췄다 복구되는 경우에도
    그 달 회차가 아예 생성되지 못해 영영 닫힌 채로 남는 일이 없다. 회차가 새로 생성돼도
    apply_end·notify_date가 이미 지난 값이면 뒤이은 close_expired_rounds/notify_due_rounds가
    같은 실행 안에서 바로 closed·notified까지 처리한다.
    """
    year, month = villa_router.target_month_for_date(today)
    villa_router.get_or_create_round(db, year, month)

    prev_year, prev_month = villa_router.shift_month(year, month, -1)
    villa_router.get_or_create_round(db, prev_year, prev_month)


def close_expired_rounds(db: Session, today) -> int:
    """접수 마감일이 지난 회차를 닫는다. status 자체가 중복 실행 방지 역할을 한다."""
    rounds = db.query(models.VillaBookingRound).filter(
        models.VillaBookingRound.status == "open",
        models.VillaBookingRound.apply_end < today,
    ).all()
    for booking_round in rounds:
        booking_round.status = "closed"
        logger.info(
            f"villa round {booking_round.target_year}-{booking_round.target_month} closed"
        )
    return len(rounds)


def send_deadline_reminders(db: Session, today) -> int:
    """마감 임박 리마인더. reminder_sent 플래그로 1회만 보낸다."""
    rounds = db.query(models.VillaBookingRound).filter(
        models.VillaBookingRound.status == "open",
        models.VillaBookingRound.reminder_sent == False,
    ).all()

    sent = 0
    for booking_round in rounds:
        days_left = (booking_round.apply_end - today).days
        if 0 <= days_left <= REMINDER_DAYS_BEFORE:
            villa_notify.notify_admins_deadline_soon(
                db, booking_round, _pending_count(db, booking_round.id)
            )
            booking_round.reminder_sent = True
            sent += 1
    return sent


def notify_due_rounds(db: Session, today) -> dict:
    """
    통보일이 된 회차의 결과를 발송한다.
    미확정 경합이 남아 있으면 임의로 선정하지 않고 보류한 뒤 관리자에게 1회 경고한다.
    """
    rounds = db.query(models.VillaBookingRound).filter(
        models.VillaBookingRound.status == "closed",
        models.VillaBookingRound.notify_date <= today,
    ).all()

    result = {"notified_rounds": 0, "confirmed": 0, "rejected": 0, "blocked": 0}

    for booking_round in rounds:
        pending = _pending_count(db, booking_round.id)
        if pending:
            result["blocked"] += 1
            if not booking_round.notify_warning_sent:
                villa_notify.notify_admins_notify_blocked(db, booking_round, pending)
                booking_round.notify_warning_sent = True
            continue

        targets = db.query(models.VillaReservation).filter(
            models.VillaReservation.round_id == booking_round.id,
            models.VillaReservation.status.in_(("confirmed", "rejected")),
            models.VillaReservation.notified_confirmed == False,
        ).all()

        for reservation in targets:
            if reservation.status == "confirmed":
                villa_notify.notify_confirmed(db, reservation)
                result["confirmed"] += 1
            else:
                villa_notify.notify_rejected(db, reservation)
                result["rejected"] += 1
            reservation.notified_confirmed = True

        booking_round.status = "notified"
        result["notified_rounds"] += 1

    return result


def run(db: Session) -> dict:
    """날짜 기반 작업을 한 번 실행한다. 모든 단계가 멱등하도록 플래그로 보호된다."""
    today = datetime.now().date()

    ensure_current_round(db, today)
    closed = close_expired_rounds(db, today)
    reminders = send_deadline_reminders(db, today)

    # SessionLocal이 autoflush=False라 앞 단계의 status 변경이 아직 DB 쿼리에 보이지 않는다.
    # flush하지 않으면 방금 closed로 바꾼 회차를 통보 단계가 놓쳐 한 주기를 더 기다리게 된다.
    db.flush()

    notified = notify_due_rounds(db, today)
    db.commit()

    return {"closed": closed, "reminders": reminders, **notified}


def scheduled_job():
    """APScheduler 진입점. 실패가 다른 작업에 번지지 않도록 세션과 예외를 분리한다."""
    db = SessionLocal()
    try:
        summary = run(db)
        if any(summary.values()):
            logger.info(f"villa scheduler: {summary}")
    except Exception as e:
        logger.error(f"villa scheduler failed: {e}")
        db.rollback()
    finally:
        db.close()
