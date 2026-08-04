"""
Minimal client for the Safaricom Daraja "Lipa Na M-Pesa Online" (STK
Push) API. Talks to DARAJA_BASE_URL from settings (sandbox by default).

Note for this delivery environment specifically: the sandboxed
container this code was developed and tested in only has network
egress to package registries (PyPI, npm, GitHub) -- not
sandbox.safaricom.co.ke -- so the live HTTP calls below could not be
exercised end-to-end here. Everything around them (Payment/Invoice
creation, the callback parser, status transitions, notifications,
receipts) was verified with simulated Daraja responses. Test this
module's actual network calls against real Daraja sandbox credentials
before relying on it in production.
"""
import base64
from datetime import datetime

import requests
from django.conf import settings


class DarajaError(Exception):
    """Raised for any failure talking to Daraja -- a bad HTTP status,
    a timeout, or a response missing the fields we need."""


def _get_access_token():
    url = f'{settings.DARAJA_BASE_URL}/oauth/v1/generate?grant_type=client_credentials'
    try:
        response = requests.get(
            url, auth=(settings.DARAJA_CONSUMER_KEY, settings.DARAJA_CONSUMER_SECRET), timeout=15,
        )
        response.raise_for_status()
        token = response.json().get('access_token')
        if not token:
            raise DarajaError('Daraja did not return an access token.')
        return token
    except requests.RequestException as exc:
        raise DarajaError(f'Could not reach Daraja to get an access token: {exc}') from exc


def _password_and_timestamp():
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    raw = f'{settings.DARAJA_SHORTCODE}{settings.DARAJA_PASSKEY}{timestamp}'
    password = base64.b64encode(raw.encode()).decode()
    return password, timestamp


def normalize_phone_number(phone_number):
    """Daraja expects 2547XXXXXXXX / 2541XXXXXXXX -- no plus, no leading 0."""
    digits = ''.join(ch for ch in phone_number if ch.isdigit())
    if digits.startswith('0'):
        digits = '254' + digits[1:]
    elif digits.startswith('7') or digits.startswith('1'):
        digits = '254' + digits
    elif digits.startswith('254'):
        pass
    else:
        raise DarajaError(f'"{phone_number}" does not look like a valid Kenyan phone number.')
    if len(digits) != 12:
        raise DarajaError(f'"{phone_number}" does not look like a valid Kenyan phone number.')
    return digits


def stk_push(phone_number, amount, account_reference, transaction_desc):
    """Initiates an STK Push prompt on the customer's phone. Returns the
    parsed JSON dict (MerchantRequestID, CheckoutRequestID, ResponseCode,
    ResponseDescription, CustomerMessage) on success."""
    token = _get_access_token()
    password, timestamp = _password_and_timestamp()
    normalized_phone = normalize_phone_number(phone_number)

    payload = {
        'BusinessShortCode': settings.DARAJA_SHORTCODE,
        'Password': password,
        'Timestamp': timestamp,
        'TransactionType': 'CustomerPayBillOnline',
        'Amount': int(amount),
        'PartyA': normalized_phone,
        'PartyB': settings.DARAJA_SHORTCODE,
        'PhoneNumber': normalized_phone,
        'CallBackURL': settings.DARAJA_CALLBACK_URL,
        'AccountReference': account_reference[:12],
        'TransactionDesc': transaction_desc[:13] or 'Payment',
    }

    try:
        response = requests.post(
            f'{settings.DARAJA_BASE_URL}/mpesa/stkpush/v1/processrequest',
            json=payload, headers={'Authorization': f'Bearer {token}'}, timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise DarajaError(f'STK push request failed: {exc}') from exc

    data = response.json()
    if 'CheckoutRequestID' not in data:
        raise DarajaError(data.get('errorMessage') or 'Daraja did not return a CheckoutRequestID.')
    return data


def stk_query(checkout_request_id):
    """Actively queries the status of a previously-initiated STK push --
    used for the "Verify Payment" action when a callback never arrived."""
    token = _get_access_token()
    password, timestamp = _password_and_timestamp()

    payload = {
        'BusinessShortCode': settings.DARAJA_SHORTCODE,
        'Password': password,
        'Timestamp': timestamp,
        'CheckoutRequestID': checkout_request_id,
    }

    try:
        response = requests.post(
            f'{settings.DARAJA_BASE_URL}/mpesa/stkpushquery/v1/query',
            json=payload, headers={'Authorization': f'Bearer {token}'}, timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise DarajaError(f'STK status query failed: {exc}') from exc

    return response.json()
