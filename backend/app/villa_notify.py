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


def guide_url(reservation_id: int) -> str:
    return f"{PUBLIC_BASE_URL.rstrip('/')}/villa/guide/{reservation_id}"


def checkout_url(reservation_id: int) -> str:
    return f"{PUBLIC_BASE_URL.rstrip('/')}/villa/checkout/{reservation_id}"


def admin_villa_url() -> str:
    return f"{PUBLIC_BASE_URL.rstrip('/')}/admin/villa"


def _admin_link_lines() -> tuple:
    """관리자 알림 끝에 붙이는 관리자 페이지 링크. (slack용, mail용) 문구를 튜플로 반환한다."""
    url = admin_villa_url()
    return f"\n👉 <{url}|[관리자 페이지]>", f"\n[관리자 페이지] {url}\n"


# 동비재 주차등록 요청 메일. 청평별장은 관리실 등록 절차가 없어 동비재만 대상이다.
PARKING_MAIL_VILLA = "동비재"
PARKING_MAIL_SUBJECT = "102동1201호 주차등록 부탁드립니다."
PARKING_CANCEL_SUBJECT = "102동1201호 주차등록·입실 취소 부탁드립니다."


# 1박 5만원, 이후 1박마다 3만원 추가 (예: 3박 = 5+3+3 = 11만원)
FEE_FIRST_NIGHT = 50000
FEE_EXTRA_NIGHT = 30000
PAYMENT_ACCOUNT = "기업은행 592-027426-01-020 (예금주: 김다회)"


def usage_fee(nights: int) -> int:
    if nights < 1:
        return 0
    return FEE_FIRST_NIGHT + (nights - 1) * FEE_EXTRA_NIGHT


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


def _dispatch_slack_only(user, message: str) -> bool:
    """Slack DM만 보낸다. 메일함이 아니라 현장에서 바로 봐야 하는 당일 알림에 쓴다."""
    if not user or not user.email:
        logger.warning("이메일이 없어 통보를 건너뜁니다.")
        return False
    try:
        slack_user_id = slack_utils.get_slack_user_id_by_email(user.email)
        if slack_user_id:
            slack_utils.send_slack_dm(slack_user_id, message)
            return True
    except Exception as e:
        logger.error(f"Slack 통보 실패 ({user.email}): {e}")
    return False


def _boundary_notice_lines(reservation) -> list:
    """
    앞뒤로 붙는 예약이 있어 정규 시간이 강제된 경우의 안내 문구.
    겹치는 예약이 없는 경계는 신청한 시간을 그대로 쓰므로 별도 안내가 없다.
    """
    lines = []
    if reservation.checkin_time_forced:
        lines.append(
            f"⚠️ 입실일에 다른 예약자의 퇴실이 겹쳐, 정리 시간을 위해 "
            f"입실 시간을 정규 시간인 {reservation.checkin_time}으로 지켜주셔야 합니다."
        )
    if reservation.checkout_time_forced:
        lines.append(
            f"⚠️ 퇴실일에 다른 예약자의 입실이 겹쳐, 정리 시간을 위해 "
            f"퇴실 시간을 정규 시간인 {reservation.checkout_time}으로 지켜주셔야 합니다."
        )
    return lines


def notify_confirmed(db: Session, reservation) -> bool:
    """확정 통보. 이용료 입금 안내와 차량·이용구성을 입력할 링크를 함께 보낸다."""
    villa = _villa_name(reservation)
    period = _period(reservation)
    link = extra_info_url(reservation.id)
    boundary_lines = _boundary_notice_lines(reservation)
    boundary_block = ("\n" + "\n".join(boundary_lines) + "\n") if boundary_lines else ""

    nights = (reservation.end_date - reservation.start_date).days
    fee = usage_fee(nights)

    slack_message = (
        f"🏡 *[비트별장 예약 확정 안내]*\n\n"
        f"*{villa}* 예약이 확정되었습니다.\n"
        f"• *이용 기간*: {period}\n"
        f"• *입실/퇴실*: {reservation.checkin_time} / {reservation.checkout_time}\n"
        f"• *사용 인원*: {reservation.participant_count}명\n"
        f"{boundary_block}\n"
        f"💰 *이용료 안내*\n"
        f"• 이용료: {nights}박 {fee:,}원 (1박 5만원, 추가 1박당 3만원)\n"
        f"• 입금 계좌: {PAYMENT_ACCOUNT}\n"
        f"• 입금 기한: 예약 확정일로부터 3일 이내 필수\n\n"
        f"아래 링크에서 차량 정보와 이용 구성을 입력해 주세요.\n{link}"
    )
    mail_body = (
        f"{villa} 예약이 확정되었습니다.\n\n"
        f"- 이용 기간: {period}\n"
        f"- 입실/퇴실: {reservation.checkin_time} / {reservation.checkout_time}\n"
        f"- 사용 인원: {reservation.participant_count}명\n"
        f"{boundary_block}\n"
        f"[이용료 안내]\n"
        f"- 이용료: {nights}박 {fee:,}원 (1박 5만원, 추가 1박당 3만원)\n"
        f"- 입금 계좌: {PAYMENT_ACCOUNT}\n"
        f"- 입금 기한: 예약 확정일로부터 3일 이내 필수\n\n"
        f"아래 링크에서 차량 정보와 이용 구성(성인/아동)을 입력해 주세요.\n"
        f"{link}\n\n"
        f"링크 접속에는 사내 SSO 로그인이 필요하며, 본인 예약만 조회됩니다.\n"
    )
    return _dispatch(db, reservation.user, f"[BIT] {villa} 예약이 확정되었습니다", slack_message, mail_body)


def notify_boundary_time_forced(db: Session, reservation, side: str) -> bool:
    """
    이미 확정되어 있던 예약의 경계에 새로운 예약이 붙어, 정규 시간 준수가 새로
    필요해졌을 때 보내는 알림. side='checkin'이면 입실일 겹침, 'checkout'이면 퇴실일 겹침.
    """
    villa = _villa_name(reservation)
    period = _period(reservation)

    if side == "checkin":
        title = "입실 시간 정규화 안내"
        detail = (
            f"입실일({reservation.start_date})에 다른 예약자의 퇴실 일정이 겹치게 되어, "
            f"정리 시간을 위해 입실 시간을 정규 시간인 *{reservation.checkin_time}*으로 지켜주셔야 합니다."
        )
    else:
        title = "퇴실 시간 정규화 안내"
        detail = (
            f"퇴실일({reservation.end_date})에 다른 예약자의 입실 일정이 겹치게 되어, "
            f"정리 시간을 위해 퇴실 시간을 정규 시간인 *{reservation.checkout_time}*으로 지켜주셔야 합니다."
        )

    slack_message = (
        f"🕐 *[비트별장 {title}]*\n\n"
        f"*{villa}* {period} 예약에 안내드립니다.\n"
        f"{detail}"
    )
    mail_body = (
        f"{villa} {period} 예약에 안내드립니다.\n\n"
        f"{detail.replace('*', '')}\n"
    )
    return _dispatch(db, reservation.user, f"[BIT] {villa} {title}", slack_message, mail_body)


def notify_checkin_guide(db: Session, reservation) -> bool:
    """입실 전날 발송하는 이용안내 링크. 출입방법·와이파이 등은 별장마다 달라 페이지로 연결한다."""
    villa = _villa_name(reservation)
    period = _period(reservation)
    link = guide_url(reservation.id)

    slack_message = (
        f"🏡 *[{villa} 이용안내]*\n\n"
        f"내일부터 예약하신 *{villa}* 이용이 시작됩니다.\n"
        f"• *이용 기간*: {period}\n\n"
        f"출입방법·와이파이 등 이용안내를 아래 링크에서 확인해 주세요.\n{link}"
    )
    mail_body = (
        f"내일부터 예약하신 {villa} 이용이 시작됩니다.\n\n"
        f"- 이용 기간: {period}\n\n"
        f"출입방법·와이파이 등 이용안내를 아래 링크에서 확인해 주세요.\n"
        f"{link}\n\n"
        f"링크 접속에는 사내 SSO 로그인이 필요하며, 본인 예약만 조회됩니다.\n"
    )
    return _dispatch(db, reservation.user, f"[BIT] {villa} 이용안내", slack_message, mail_body)


def notify_checkout_reminder(db: Session, reservation) -> bool:
    """퇴실일 오전 발송하는 퇴실 체크사항 링크. 슬랙으로만 보낸다."""
    villa = _villa_name(reservation)
    link = checkout_url(reservation.id)

    slack_message = (
        f"🧹 *[{villa} 퇴실 체크사항]*\n\n"
        f"오늘({reservation.end_date}) 퇴실일입니다.\n"
        f"아래 링크에서 퇴실 전 체크사항을 확인하고 체크·제출해 주세요.\n{link}"
    )
    return _dispatch_slack_only(reservation.user, slack_message)


def notify_admins_checkout_submitted(db: Session, reservation, checklist_items, checked, notes) -> int:
    """퇴실 체크사항 제출 결과를 별장 관리 담당자에게 슬랙으로 알린다."""
    villa = _villa_name(reservation)
    period = _period(reservation)
    applicant = reservation.user.name if reservation.user else "(알 수 없음)"

    lines = []
    for item, done in zip(checklist_items, checked):
        mark = "✅" if done else "❌"
        lines.append(f"{mark} {item['label']}")
    checklist_block = "\n".join(lines)
    notes_block = f"\n\n📝 *특이사항*\n{notes}" if notes else ""
    admin_slack_link, admin_mail_link = _admin_link_lines()

    slack_message = (
        f"🧹 *[{villa} 퇴실 체크사항 제출]*\n\n"
        f"*{applicant}* 님이 퇴실 체크사항을 제출했습니다.\n"
        f"• *기간*: {period}\n\n"
        f"{checklist_block}"
        f"{notes_block}"
        f"{admin_slack_link}"
    )
    mail_body = (
        f"{applicant} 님이 {villa} 퇴실 체크사항을 제출했습니다.\n\n"
        f"기간: {period}\n\n"
        + "\n".join(f"[{'V' if done else ' '}] {item['label']}" for item, done in zip(checklist_items, checked))
        + (f"\n\n특이사항: {notes}\n" if notes else "\n")
        + admin_mail_link
    )
    return _notify_admins(db, f"[BIT] {villa} 퇴실 체크사항 제출 ({applicant})", slack_message, mail_body)


def parking_mail_draft(reservation) -> dict:
    """
    관리실에 보낼 주차등록 요청 메일의 초안. 이용자가 이 내용을 확인·수정한 뒤
    발송하므로, 여기서는 확정된 예약 정보를 그대로 채워 넣는 데까지만 한다.
    """
    applicant = reservation.user.name if reservation.user else "(알 수 없음)"
    return {
        "subject": PARKING_MAIL_SUBJECT,
        "body": (
            f"안녕하세요, 비트컴퓨터입니다.\n"
            f"아래 숙소 이용자의 차량 주차등록을 부탁드립니다.\n\n"
            f"- 이용자: {applicant}\n"
            f"- 연락처: {reservation.contact_phone or '미입력'}\n"
            f"- 이용기간: {_period(reservation)}\n"
            f"- 차량번호: {reservation.vehicle_numbers or '미입력'}\n\n"
            f"감사합니다.\n"
        ),
    }


def send_parking_mail(db: Session, to_email: str, subject: str, body: str) -> None:
    """
    다른 통보와 달리 예외를 삼키지 않는다 — 이용자가 발송 버튼을 누르고 결과를
    기다리는 흐름이라, 조용히 실패하면 등록이 된 줄 알고 넘어가게 된다.
    """
    email_utils.send_mail_or_raise(db, to_email, subject, body)


def parking_cancel_mail_body(reservation, reason: str) -> str:
    applicant = reservation.user.name if reservation.user else "(알 수 없음)"
    return (
        f"안녕하세요, 비트컴퓨터입니다.\n"
        f"아래 숙소 이용 예약이 취소되어, 주차등록과 입실을 취소 부탁드립니다.\n\n"
        f"- 이용자: {applicant}\n"
        f"- 연락처: {reservation.contact_phone or '미입력'}\n"
        f"- 이용기간: {_period(reservation)}\n"
        f"- 차량번호: {reservation.vehicle_numbers or '미입력'}\n"
        f"- 취소 사유: {reason or '미기재'}\n\n"
        f"감사합니다.\n"
    )


def send_parking_cancel_mail(db: Session, to_email: str, reservation, reason: str) -> bool:
    """
    동비재 예약이 취소될 때 관리실에 주차·입실 취소를 알린다. 취소 자체는 이미
    끝난 뒤의 부가 통보이므로, 발송 실패가 취소를 되돌리지 않도록 예외를 삼킨다.
    """
    return email_utils.send_mail(db, to_email, PARKING_CANCEL_SUBJECT, parking_cancel_mail_body(reservation, reason))


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


def notify_canceled_by_admin(db: Session, reservation, reason: str) -> bool:
    """
    담당자가 이용자의 예약을 직접 취소했을 때 이용자에게 보내는 통보.
    이용자가 취소를 요청한 게 아니므로 '승인'이 아니라 '관리자 취소'로 안내하고,
    모르고 방문하는 일이 없도록 사유를 함께 전한다.
    """
    villa = _villa_name(reservation)
    period = _period(reservation)

    slack_message = (
        f"🏡 *[비트별장 예약 취소 안내]*\n\n"
        f"*{villa}* {period} 예약이 관리자에 의해 취소되었습니다.\n"
        f"• *사유*: {reason}\n\n"
        f"문의가 있으시면 관리팀으로 연락해 주세요."
    )
    mail_body = (
        f"{villa} {period} 예약이 관리자에 의해 취소되었습니다.\n\n"
        f"- 사유: {reason}\n\n"
        f"문의가 있으시면 관리팀으로 연락해 주세요.\n"
    )
    return _dispatch(db, reservation.user, f"[BIT] {villa} 예약이 취소되었습니다", slack_message, mail_body)


def villa_admin_recipients(db: Session):
    """
    비트별장 관리 알림을 받을 대상. 별장 위임 관리자가 지정돼 있으면 그 담당자만
    받는다 — 전체 관리자의 알림 부담을 줄이려고 위임하는 것이므로, 위임 후에도
    전체 관리자에게 계속 보내면 위임의 의미가 없다. 위임 담당자가 없으면(아직
    지정하지 않았거나 전부 해제된 경우) 안전한 기본값으로 전체 관리자에게 보낸다.
    """
    from . import models  # 순환 import를 피해 함수 안에서 가져온다

    villa_managers = db.query(models.User).filter(
        models.User.is_villa_admin == True,
        models.User.email.isnot(None),
    ).all()
    if villa_managers:
        return villa_managers

    return db.query(models.User).filter(
        models.User.role == "admin",
        models.User.email.isnot(None),
    ).all()


def _notify_admins(db: Session, subject: str, slack_message: str, mail_body: str) -> int:
    admins = villa_admin_recipients(db)

    sent = 0
    for admin in admins:
        if _dispatch(db, admin, subject, slack_message, mail_body):
            sent += 1

    if sent == 0:
        # 관리자 계정에 이메일이 없으면 알림이 조용히 사라진다. 로그로 드러낸다.
        logger.warning(f"관리자 알림을 아무에게도 보내지 못했습니다: {subject}")
    return sent


def notify_admins_new_application(db: Session, reservation, is_open_booking: bool) -> int:
    """
    예약 신청이 접수될 때마다(정규예약 대기, 선착순 대기 모두 관리자 확정이 필요하다)
    관리자에게 알린다. 취소 요청과 달리 방치 위험은 없지만, 관리자가 접수 현황을
    실시간으로 파악하고 싶다는 요청에 따라 매 신청마다 보낸다.
    """
    villa = _villa_name(reservation)
    period = _period(reservation)
    applicant = reservation.user.name if reservation.user else "(알 수 없음)"
    dept = f" · {reservation.user.department}" if reservation.user and reservation.user.department else ""

    if is_open_booking:
        title = "선착순 예약 신청"
        detail = "정규예약 마감 후 남은 날짜에 대한 선착순 신청입니다. 중복 신청은 불가하니 관리자 페이지에서 확정 처리를 해주세요."
    else:
        title = "새 예약 신청"
        detail = "정규예약 접수중입니다. 마감 후 관리자 페이지에서 확정 처리를 해주세요."

    admin_slack_link, admin_mail_link = _admin_link_lines()

    slack_message = (
        f"📋 *[비트별장 {title}]*\n\n"
        f"*{applicant}*{dept} 님이 신청했습니다.\n"
        f"• *별장*: {villa}\n"
        f"• *기간*: {period}\n"
        f"• *인원*: {reservation.participant_count}명\n\n"
        f"{detail}"
        f"{admin_slack_link}"
    )
    mail_body = (
        f"{applicant}{dept} 님이 비트별장을 신청했습니다.\n\n"
        f"- 별장: {villa}\n"
        f"- 기간: {period}\n"
        f"- 인원: {reservation.participant_count}명\n\n"
        f"{detail}\n"
        + admin_mail_link
    )
    return _notify_admins(db, f"[BIT] 비트별장 {title}", slack_message, mail_body)


def notify_admins_deadline_soon(db: Session, booking_round, pending_count: int) -> int:
    """접수 마감이 임박했음을 관리자에게 알린다."""
    label = f"{booking_round.target_year}년 {booking_round.target_month}월"
    admin_slack_link, admin_mail_link = _admin_link_lines()
    slack_message = (
        f"⏰ *[비트별장 정규예약 마감 임박]*\n\n"
        f"*{label}* 대상 접수가 {booking_round.apply_end}에 마감됩니다.\n"
        f"• *대기 중인 신청*: {pending_count}건\n\n"
        f"마감 후 확정 처리를 완료해야 결과가 통보됩니다."
        f"{admin_slack_link}"
    )
    mail_body = (
        f"{label} 대상 비트별장 정규예약 접수가 {booking_round.apply_end}에 마감됩니다.\n"
        f"대기 중인 신청: {pending_count}건\n\n"
        f"마감 후 관리자 페이지에서 확정 처리를 완료해 주세요.\n"
        + admin_mail_link
    )
    return _notify_admins(db, f"[BIT] 비트별장 {label} 접수 마감 임박", slack_message, mail_body)


def notify_admins_notify_blocked(db: Session, booking_round, pending_count: int) -> int:
    """통보일이 지났는데 미확정 경합이 남아 통보를 보류했음을 알린다."""
    label = f"{booking_round.target_year}년 {booking_round.target_month}월"
    admin_slack_link, admin_mail_link = _admin_link_lines()
    slack_message = (
        f"🚨 *[비트별장 결과 통보 보류]*\n\n"
        f"*{label}* 대상 통보일({booking_round.notify_date})이 지났지만 "
        f"확정되지 않은 신청이 *{pending_count}건* 남아 있습니다.\n\n"
        f"임의로 선정하지 않고 통보를 보류했습니다. "
        f"관리자 페이지에서 확정을 마치면 결과가 발송됩니다."
        f"{admin_slack_link}"
    )
    mail_body = (
        f"{label} 대상 비트별장 결과 통보가 보류되었습니다.\n\n"
        f"통보일: {booking_round.notify_date}\n"
        f"미확정 신청: {pending_count}건\n\n"
        f"임의 선정을 하지 않는 정책이므로, 관리자 페이지에서 확정을 마쳐 주세요.\n"
        + admin_mail_link
    )
    return _notify_admins(db, f"[BIT] 비트별장 {label} 결과 통보 보류", slack_message, mail_body)


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
