import os
import requests
import logging

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
logger = logging.getLogger(__name__)

def get_slack_user_id_by_email(email: str) -> str:
    """이메일로 Slack User ID를 조회합니다."""
    if not SLACK_BOT_TOKEN or not email:
        return None
        
    url = "https://slack.com/api/users.lookupByEmail"
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    try:
        response = requests.get(url, headers=headers, params={"email": email}, timeout=5)
        response.raise_for_status()
        data = response.json()
        if data.get("ok"):
            return data["user"]["id"]
        else:
            logger.warning(f"Slack lookup failed for {email}: {data.get('error')}")
            return None
    except Exception as e:
        logger.error(f"Slack API error: {e}")
        return None

def send_slack_dm(user_id: str, message: str):
    """Slack User ID로 DM을 발송합니다."""
    if not SLACK_BOT_TOKEN or not user_id:
        return
        
    url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {
        "channel": user_id,
        "text": message
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=5)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            logger.warning(f"Slack DM send failed: {data.get('error')}")
    except Exception as e:
        logger.error(f"Slack DM send exception: {e}")

def notify_reservation_preempted(email: str, old_start_time: str, new_user_name: str, new_priority: str):
    """예약 교체(취소) 시 Slack 알림 발송"""
    if not email:
        return
        
    slack_user_id = get_slack_user_id_by_email(email)
    if not slack_user_id:
        return
        
    message = (
        f"🚨 *[스크린 골프 예약 취소 알림]*\n\n"
        f"회원님이 예약하신 *{old_start_time}* 스크린 골프 우선순위가 더 높은(*{new_priority}*) 직원({new_user_name})에 의해 교체되어 취소되었습니다.\n"
        f"다른 시간대를 이용해 주시기 바랍니다."
    )
    
    send_slack_dm(slack_user_id, message)

def notify_upcoming_reservation(email: str, start_time: str, participant_count: int):
    """예약 1시간 전 Slack 사전 알림 발송"""
    if not email:
        return
        
    slack_user_id = get_slack_user_id_by_email(email)
    if not slack_user_id:
        return
        
    message = (
        f"⏳ *[스크린 골프 이용 안내]*\n\n"
        f"회원님이 예약하신 스크린 골프 이용 시간이 약 1시간 남았습니다.\n"
        f"• *예약 시간*: {start_time} 부터 {participant_count}시간\n\n"
        f"즐거운 시간 되시길 바랍니다! ⛳️"
    )
    
    send_slack_dm(slack_user_id, message)

