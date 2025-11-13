from django.utils import timezone
from .models import Notification
import requests, smtplib, json
from email.mime.text import MIMEText

def dispatch_notification(notif: Notification):
    """Routes to the correct send method based on channel."""
    if notif.channel == Notification.Channel.EMAIL:
        return _send_email(notif)
    elif notif.channel == Notification.Channel.SMS:
        return _send_sms(notif)
    elif notif.channel == Notification.Channel.PUSH:
        return _send_push(notif)
    elif notif.channel == Notification.Channel.WEBHOOK:
        return _send_webhook(notif)
    else:
        raise ValueError(f"Unsupported channel: {notif.channel}")


def _send_email(notif: Notification):
    """Send an email (simple SMTP stub — extend with SendGrid later)."""
    try:
        msg = MIMEText(notif.message)
        msg["Subject"] = notif.subject or "ERP Notification"
        msg["From"] = "no-reply@erp.local"
        msg["To"] = notif.to
        # Example: using localhost SMTP relay (dummy for now)
        with smtplib.SMTP("localhost") as s:
            s.sendmail(msg["From"], [notif.to], msg.as_string())
        notif.status = Notification.Status.SENT
        notif.sent_at = timezone.now()
        notif.save(update_fields=["status", "sent_at"])
        return True
    except Exception as e:
        notif.status = Notification.Status.FAILED
        notif.error = str(e)
        notif.save(update_fields=["status", "error"])
        raise


def _send_sms(notif: Notification):
    """Placeholder for SMS API (Twilio, Msgkart, etc.)"""
    # Integrate: requests.post("https://api.msgkart.com/send", data={...})
    notif.status = Notification.Status.SENT
    notif.sent_at = timezone.now()
    notif.save(update_fields=["status", "sent_at"])
    return True


def _send_push(notif: Notification):
    """Placeholder for mobile push notifications."""
    notif.status = Notification.Status.SENT
    notif.sent_at = timezone.now()
    notif.save(update_fields=["status", "sent_at"])
    return True


def _send_webhook(notif: Notification):
    """Send payload to a webhook endpoint."""
    if not notif.to.startswith("http"):
        raise ValueError("Invalid webhook URL.")
    resp = requests.post(notif.to, json=notif.payload or {"message": notif.message})
    if resp.status_code >= 200 and resp.status_code < 300:
        notif.status = Notification.Status.SENT
        notif.sent_at = timezone.now()
    else:
        notif.status = Notification.Status.FAILED
        notif.error = f"HTTP {resp.status_code}: {resp.text[:250]}"
    notif.save(update_fields=["status", "sent_at", "error"])
    return notif.status == Notification.Status.SENT



def enqueue_once(channel, to, subject, message, payload=None, dedupe_key=None):
    """
    Enqueue notification only once per request using a dedupe_key.
    dedupe_key example: f"{location_id}-{batch_id}-LOW_STOCK"
    """
    if dedupe_key:
        if Notification.objects.filter(payload__dedupe_key=dedupe_key).exists():
            return  # Skip duplicate

    Notification.objects.create(
        channel=channel,
        to=to,
        subject=subject,
        message=message,
        payload={"dedupe_key": dedupe_key, **(payload or {})},
        status=Notification.Status.QUEUED,
        created_at=timezone.now(),
    )

