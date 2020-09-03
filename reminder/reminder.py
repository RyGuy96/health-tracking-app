#!/usr/bin/env python

"""reminder.py: Sends a sms to remind a user to submit data at set intervals using cloud service scheduler."""

from twilio.twiml.messaging_response import MessagingResponse
import gspread
import re
import datetime
import time
from twilio.rest import Client
from oauth2client.service_account import ServiceAccountCredentials
import pytz
import sys


def open_spreadsheet() -> object:
    """Authorize Google Drive access and return spreadsheet reference."""
    
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    credentials = ServiceAccountCredentials.from_json_keyfile_name('JSON_FILE', scope)
    gc = gspread.authorize(credentials)
    wks_health = gc.open("Health Tracker").sheet1
    return wks_health


def get_date() -> datetime:
    utc_now = pytz.utc.localize(datetime.datetime.utcnow())
    return datetime.datetime.strftime(utc_now.astimezone(pytz.timezone("America/Chicago")), '%Y-%m-%d')


def entry_today() -> str:
    wks_health = open_spreadsheet()
    date_last_entry = wks_health.acell('A2').value
    date_today = get_date()
    if date_today == date_last_entry:
        return "yes"
    else:
        return "no"


def sms_sender(message_text: str, recipient_num:str) -> None:
    """Define credentials for Twilio API sms."""

    # Find these values at https://twilio.com/user/account, (note that this is not a secure method)
    account_sid = "YOUR_SID"
    auth_token = "YOUR_AUTH_TOKEN"
    client = Client(account_sid, auth_token)
    message = client.api.account.messages.create(to= recipient_num,
                                                    from_="YOUR_TWILIO_NUMBER",
                                                    body= message_text)


def reminder() -> None:
    """Send reminder if no entry as of certian times"""

    utc_now = pytz.utc.localize(datetime.datetime.utcnow())
    # Heroku scheduler usually runs a couple mins after hour, not at top, so just hour compared
    now = datetime.datetime.strftime(utc_now.astimezone(pytz.timezone("America/Chicago")), '%I: %p')
    if now in ["11: AM", "02: PM", "05: PM", "08: PM"]:
        if entry_today() == "no":
            sms_sender("I haven't heard from you today. How are you feeling? Reply with a # for: sleep, stress, joints,"
                       " energy, and your mood.", "+12064036747")

if __name__ == "__main__":
    reminder()
