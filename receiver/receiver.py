
#!/usr/bin/env python

"""receiver.py: Receives an sms message to a specifind number; parses and saves data in a Google Spreadsheet."""

from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import gspread
import re
import datetime
import time
from twilio.rest import Client
from oauth2client.service_account import ServiceAccountCredentials
import pytz

NUM_OF_RATINGS = 5
MEDS_CELL = chr(ord('a') + 1 + NUM_OF_RATINGS) + "2"

def sms_sender(message_text: str, recipient_num: str) -> None:
    """Define credentials for Twilio API sms."""

    # Find these values at https://twilio.com/user/account (note that this is not a secure method)
    account_sid = "YOUR_SID"
    auth_token = "YOUR_AUTH_TOKEN"
    client = Client(account_sid, auth_token)
    message = client.api.account.messages.create(to= recipient_num,
                                                 from_="YOUR_TWILIO_NUMBER",
                                                 body = message_text)


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


def parse_sms(sms_reply: str) -> dict:
    """Return single dictionary of relevant values in sms."""

    # ratings
    rating_vals = re.findall(r"\b\d+\b", sms_reply)[:NUM_OF_RATINGS]

    # added meds
    add_meds = re.findall(r"\+(.*?\))", sms_reply)

    # removed meds
    remove_meds = re.findall(r"\-(.*?\))", sms_reply)

    # notes
    note = re.compile(r"Note\((.*?)\)", flags=re.IGNORECASE)
    add_note = [] if not note.findall(sms_reply) else note.findall(sms_reply)[0]

    # help
    display_help_re = re.compile(r'help[ -]?me', flags=re.IGNORECASE)
    display_help = display_help_re.search(sms_reply) is not None

    # see meds
    display_meds_re = re.compile(r'see[ -]?meds', flags=re.IGNORECASE)
    display_meds = display_help_re.search(sms_reply) is not None

    # amend flag
    amend_flag_re = re.compile(r'amend', flags=re.IGNORECASE)
    amend_flag = True if amend_flag_re.search(sms_reply) else False
    
    parsed_response = {"ratings": rating_vals, "add meds": add_meds, "remove meds": remove_meds, "notes": add_note,
                       "display help": display_help, "display meds": display_meds, "amend": amend_flag}

    return parsed_response


def get_current_meds() -> str:
    wks_health = open_spreadsheet()
    return wks_health.acell(MEDS_CELL).value.strip('][').split(', ')


def validate_sms(parsed_response: dict) -> str:
    """Check sms and return 'Valid' or one or more error messages to be sent to user."""

    invalid_responses = []

    try:
        assert len(parsed_response["ratings"]) == NUM_OF_RATINGS
    except AssertionError:
        invalid_responses.append("Invalid number of ratings (there should be five)")

    current_meds = set(get_current_meds())
    parsed_meds = set(parsed_response['remove meds'])
    for missing_med in parsed_meds - current_meds:
        invalid_responses.append(f'Med to remove "{missing_med} not found; see your meds by replying "see-meds"')

    try:
        for med in parsed_response["add meds"]:
            assert med not in current_meds
    except AssertionError:
        invalid_responses.append("Med to be added already listed, see your meds by replying 'see-meds'")

    finally:
        if invalid_responses:
            return ", ".join(invalid_responses)
        else:
            return "Valid"


def record_sms(parsed_response: dict) -> None:
    """Log sms responses in Google Sheets."""

    note = parsed_response["notes"]
    remove = parsed_response["remove meds"]
    add = parsed_response["add meds"]
    current_meds = get_current_meds()
    revised_med_list = [med for med in current_meds if med not in remove] + add
    revised_med_list_formated = str(revised_med_list).replace("'", "")

    line = [get_date()] + parsed_response["ratings"] + [revised_med_list_formated]
    line.append(note if note else "")

    wks_health = open_spreadsheet()

    if parsed_response["amend"] == True:
        wks_health.delete_row(2)

    wks_health.insert_row(line, value_input_option='USER_ENTERED', index=2)


def help_message() -> str:
    # change symptoms as you see fit - some refactoring will be required if you you want to track more or less than five
    message = ("Respond to messages with: " 
              "\n1. Hours slept " 
              "\n2. Stress level (1-9) " 
              "\n3. Joints (1-9) " 
              "\n4. Energy (1-9) " 
              "\n5. Mood (1-9) " 
              "\n6. Add a note with NOTE(YOUR NOTE)* " 
              "\n7. Add a med with +MEDNAME(DOSE)* " 
              "\n8. Remove a med with -MEDNAME(DOSE)* " 
              "\n9. See all meds with 'see-meds'* " 
              "\n10. See this menu with 'help-me'*" 
              "\n11. Change today's values with 'amend'*" 
              "\n*Optional values in response")
    return message


def see_meds_message() -> str:
    return f'Your current meds are: {get_current_meds()}'


app = Flask(__name__)


@app.route("/sms", methods=['GET', 'POST'])
def main() -> str:
    """Listen for incoming sms and log content or reply with one or more error messages."""

    from_body = request.values.get('Body')

    resp = []
    while from_body is not None:

        try:
            sms = parse_sms(from_body)
        except:
            resp.append("issue parsing")
            break
        try:
            if sms['display help']:
                resp.append(help_message())
                break
        except:
            resp.append("issue with help message")
            break
        try:
            if sms['display meds']:
                resp.append(see_meds_message())
                break
        except:
            resp.append("issue with showing meds")
            break
        try:
            validation_val = validate_sms(sms)
        except:
            resp.append("issue validating")
            break
        try:
            if validation_val == "Valid":
                record_sms(sms)
                resp.append("Response recorded!")
                break
        except:
            resp.append("issue logging valid sms")
            break
        try:
            if validation_val != "Valid":
                resp.append(validation_val)
                break
        except:
            resp.append("issue logging invalid sms")
            break

    mess= MessagingResponse()
    mess.message(str(", ".join(resp)))

    return str(mess)


if __name__ == "__main__":
    app.run(debug=True)
