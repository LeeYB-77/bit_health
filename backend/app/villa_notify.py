# 비트별장 예약 통보(Slack DM + 메일)를 조립하고 발송하는 모듈
import logging
import os

from sqlalchemy.orm import Session

from . import email_utils, slack_utils

logger = logging.getLogger(__name__)

# 메일 본문의 추가입력 링크는 절대 주소여야 한다.
# README 3)의 원칙대로 https 주소를 기본값으로 둔다.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://book.bit.kr")


def extra_info_url(reservation_id: int) -> str:
    return f"{PUBLIC_BASE_URL.rstrip('/')}/villa/extra/{reservation_id}"


def _villa_name(reservation) -> str:
    return reservation.facility.name if reservation.facility else "비트별장"


def _period(reservation) -> str:
    nights = (reservation.end_date - reservation.start_date).days
    return f"{reservation.start_date} ~ {reservation.end_date} ({nights}박)"


def _dispatch(db: Session, user, subject: str, slack_message: str, mail_body: str) -> bool:
    """
    Slack과 메일을 함께 보낸다. 한쪽이 실패해도 다른 쪽은 시도하며,
    발송 실패가 호출자의 트랜잭션을 깨뜨리지 않도록 예외를 삼킨다.
    """
    if not user or not user.email:
        logger.warning("이메일이 없어 통보를 건너뜁니다.")
        return False

    slack_sent = False
    try:
        slack_user_id = slack_utils.get_slack_user_id_by_email(user.email)
        if slack_user_id:
            slack_utils.send_slack_dm(slack_user_id, slack_message)
            slack_sent = True
    except Exception as e:
        logger.error(f"Slack 통보 실패 ({user.email}): {e}")

    mail_sent = email_utils.send_mail(db, user.email, subject, mail_body)
    return slack_sent or mail_sent


def notify_confirmed(db: Session, reservation) -> bool:
    """확정 통보. 차량·이용구성을 입력할 링크를 함께 보낸다."""
    villa = _villa_name(reservation)
    period = _period(reservation)
    link = extra_info_url(reservation.id)

    slack_message = (
        f"🏡 *[비트별장 예약 확정 안내]*\n\n"
        f"*{villa}* 예약이 확정되었습니다.\n"
        f"• *이용 기간*: {period}\n"
        f"• *입실/퇴실*: {reservation.checkin_time} / {reservation.checkout_time}\n"
        f"• *사용 인원*: {reservation.participant_count}명\n\n"
        f"아래 링크에서 차량 정보와 이용 구성을 입력해 주세요.\n{link}"
    )
    mail_body = (
        f"{villa} 예약이 확정되었습니다.\n\n"
        f"- 이용 기간: {period}\n"
        f"- 입실/퇴실: {reservation.checkin_time} / {reservation.checkout_time}\n"
        f"- 사용 인원: {reservation.participant_count}명\n\n"
        f"아래 링크에서 차량 정보와 이용 구성(성인/아동)을 입력해 주세요.\n"
        f"{link}\n\n"
        f"링크 접속에는 사내 SSO 로그인이 필요하며, 본인 예약만 조회됩니다.\n"
    )
    return _dispatch(db, reservation.user, f"[BIT] {villa} 예약이 확정되었습니다", slack_message, mail_body)


def notify_rejected(db: Session, reservation) -> bool:
    """미선정 통보."""
    villa = _villa_name(reservation)
    period = _period(reservation)

    slack_message = (
        f"🏡 *[비트별장 예약 결과 안내]*\n\n"
        f"신청하신 *{villa}* {period} 기간은 아쉽게도 다른 분으로 확정되었습니다.\n\n"
        f"정규예약 마감 후에는 남은 날짜를 선착순으로 신청하실 수 있습니다."
    )
    mail_body = (
        f"신청하신 {villa} {period} 기간은 아쉽게도 다른 분으로 확정되었습니다.\n\n"
        f"정규예약 마감 후에는 남은 날짜를 선착순으로 신청하실 수 있습니다.\n"
    )
    return _dispatch(db, reservation.user, f"[BIT] {villa} 예약 결과 안내", slack_message, mail_body)


def notify_cancel_approved(db: Session, reservation) -> bool:
    villa = _villa_name(reservation)
    period = _period(reservation)

    slack_message = (
        f"🏡 *[비트별장 취소 승인]*\n\n"
        f"*{villa}* {period} 예약 취소가 승인되었습니다.\n"
        f"해당 기간은 다시 신청 가능 상태로 전환되었습니다."
    )
    mail_body = (
        f"{villa} {period} 예약 취소가 승인되었습니다.\n"
        f"해당 기간은 다시 신청 가능 상태로 전환되었습니다.\n"
    )
    return _dispatch(db, reservation.user, f"[BIT] {villa} 예약 취소가 승인되었습니다", slack_message, mail_body)


def notify_cancel_rejected(db: Session, reservation) -> bool:
    villa = _villa_name(reservation)
    period = _period(reservation)

    slack_message = (
        f"🏡 *[비트별장 취소 요청 반려]*\n\n"
        f"*{villa}* {period} 예약의 취소 요청이 반려되었습니다.\n"
        f"예약은 그대로 유지됩니다. 문의는 관리팀으로 연락해 주세요."
    )
    mail_body = (
        f"{villa} {period} 예약의 취소 요청이 반려되었습니다.\n"
        f"예약은 그대로 유지됩니다. 문의는 관리팀으로 연락해 주세요.\n"
    )
    return _dispatch(db, reservation.user, f"[BIT] {villa} 예약 취소 요청이 반려되었습니다", slack_message, mail_body)
