import requests
import json
from django.utils import timezone

from django.conf import settings
from email.header import Header
from email.utils import formataddr
from requests.auth import HTTPBasicAuth
from api.models.go_electric_rebate import GoElectricRebate
from api.models.go_electric_rebate_application import (
    GoElectricRebateApplication,
)
from datetime import timedelta, datetime
from api.services.ncda import (
    notify,
    get_rebates_redeemed_since,
    get_rebate,
    delete_rebate,
)
from api.constants import (
    FOUR_THOUSAND_REBATE,
    ONE_THOUSAND_REBATE,
    TWO_THOUSAND_REBATE,
)
from api.utility import get_applicant_full_name
from django_q.tasks import async_task
from func_timeout import func_timeout, FunctionTimedOut
from django.db import transaction
from django.db.models import Q


def get_email_service_token() -> str:
    client_id = settings.EMAIL["EMAIL_SERVICE_CLIENT_ID"]
    client_secret = settings.EMAIL["EMAIL_SERVICE_CLIENT_SECRET"]
    url = settings.EMAIL["CHES_AUTH_URL"]
    payload = {"grant_type": "client_credentials"}
    header = {"content-type": "application/x-www-form-urlencoded"}

    token_rs = requests.post(
        url,
        data=payload,
        auth=HTTPBasicAuth(client_id, client_secret),
        headers=header,
        verify=True,
    )
    token_rs.raise_for_status()
    return token_rs.json()["access_token"]


def send_email(
    recipient_email: str,
    application_id: str,
    message: str,
    cc_list: list,
    optional_subject="",
) -> None:
    sender_email = settings.EMAIL["SENDER_EMAIL"]
    sender_name = settings.EMAIL["SENDER_NAME"]
    url = settings.EMAIL["CHES_EMAIL_URL"]
    bcc_email = settings.EMAIL["BCC_EMAIL"]

    subject = (
        "CleanBC Go Electric - Application #{}".format(application_id)
        + optional_subject
    )
    bodyType = "html"

    auth_token = get_email_service_token()
    sender_info = formataddr((str(Header(sender_name, "utf-8")), sender_email))

    data = {
        "bcc": [bcc_email],
        "bodyType": bodyType,
        "body": message,
        "cc": cc_list,
        "delayTS": 0,
        "encoding": "utf-8",
        "from": sender_info,
        "priority": "normal",
        "subject": subject,
        "to": [recipient_email],
    }

    headers = {
        "Authorization": "Bearer " + auth_token,
        "Content-Type": "application/json",
    }

    response = requests.post(url, data=json.dumps(data), headers=headers)
    response.raise_for_status()


def send_individual_confirm(recipient_email, application_id):
    message = """\
        <html>
        <body>

        <p>
        This email was generated by the CleanBC Go Electric
        Passenger Vehicle Rebate program application.
        </p>

        <p>Thank you.</p>

        <p>
        We have received your application for a rebate under the CleanBC Go
        Electric Passenger Vehicle Rebate program. You can expect to get an email reply with the result of your application within 3 weeks.
        We are unable to speed up the application process as our screening is automated.
        </p>

        <p>Please keep this e-mail for your records.</p>

        <p>Questions?</p>

        <p>
        Please feel free to contact us at ZEVPrograms@gov.bc.ca.
        Emails asking about the status of your application will not be responded if it has not been 3 weeks since your application was submitted.
        Please check your junk/spam folder for any missed emails.
        </p>
        </body>
        </html>
        """
    send_email(recipient_email, application_id, message, cc_list=[])


def send_spouse_initial_message(recipient_email, application_id, initiator_email):
    origin = settings.CORS_ORIGIN_WHITELIST[0]
    message = """\
        <html>
        <body>

        <p>
        You are receiving this e-mail as you have been identified as a
        spouse under a household rebate application for the CleanBC Go
        Electric Passenger Vehicle Rebate program.
        </p>

        <p>
        To finish the rebate application please click on the
        following link:
        </p>

        <p>{origin}/household?q={application_id}</p>

        <p><i>
        If you are not the intended person to receive this email, please
        contact the CleanBC Go Electric Passenger Vehicle Rebate program at
        ZEVPrograms@gov.bc.ca
        </i></p>

        <p>Additional Questions?</p>

        <p>Please feel free to contact us at ZEVPrograms@gov.bc.ca</p>
        </body>
        </html>
        """.format(
        origin=origin, application_id=application_id
    )
    send_email(recipient_email, application_id, message, [initiator_email])


def send_household_confirm(recipient_email, application_id):
    message = """\
        <html>
        <body>

        <p>
        This email was generated by the CleanBC Go Electric
        Passenger Vehicle Rebate program application.
        </p>

        <p>Thank you.</p>

        <p>
        We have now received all documentation for your application for a
        household rebate under the CleanBC Go Electric Passenger Vehicle
        Rebate program. You can expect to get an email reply with the result of your application within 3 weeks.
        </p>

        <p>Please keep this e-mail for your records.</p>

        <p>Questions?</p>

        <p>Please feel free to contact us at ZEVPrograms@gov.bc.ca</p>

        </body>
        </html>
        """
    send_email(recipient_email, application_id, message, cc_list=[])


def send_reject(recipient_email, application_id, reason_for_decline):
    list_reasons = "<li>" + "</li><li>".join(reason_for_decline.split(";")) + "</li>"
    message = """\
        <html>
        <body>

        <p>This email was generated by the CleanBC Go Electric Passenger
        Vehicle Rebate program application.</p>

        <p>Dear Applicant,</p>

        <p>Your application cannot be approved due to the following issues:</p>

        <ul>
        <li>reasons</li>
        </ul>
        
        <b>You are encouraged to correct these issues and submit another application.</b>
        <p>https://goelectricbc.gov.bc.ca/</p>

        <p>Questions?</p>

        <p>Please feel free to contact us at ZEVPrograms@gov.bc.ca</p>
        </body>
        </html>
         """.replace(
        "<li>reasons</li>", list_reasons
    )

    send_email(
        recipient_email,
        application_id,
        message,
        cc_list=[],
        optional_subject=" – Identity cannot be verified",
    )


def send_approve(recipient_email, application_id, applicant_full_name, rebate_amounts):
    message = """\
        <html>
        <body>

        <p>This email was generated by the CleanBC Go Electric Passenger
        Vehicle Rebate program application.</p>

        <p>Dear {applicant_full_name},</p>

        <p>Your application has been approved for a maximum rebate amount of up to ${zev_max}. The rebate options available to you are listed below. </p>

        <p><b>Rebates for long-range ZEVs</b> (BEV, FCEV, ER-EV, and PHEV with an electric range of 85 km or more):</p>
        <ul>
        <li>
            ${zev_max} rebate for long-range ZEV purchase
          </li>
          <li>
            ${zev_max} rebate for long-range ZEV 36-month or longer lease term
          </li>
          <li>
            ${zev_mid} rebate for long-range ZEV 24-month lease term
          </li>
          <li>
            ${zev_min} rebate for long-range ZEV 12-month lease term
          </li>
        </ul>

        <p><b>Rebates for short-range PHEVs</b> (PHEV with an electric range of less than 85 km):</p>
        <ul>
        <li>
            ${phev_max} rebate for short-range PHEV purchase
          </li>
          <li>
            ${phev_max} rebate for short-range PHEV 36-month or longer lease term
          </li>
          <li>
            ${phev_mid} rebate for short-range PHEV 24-month lease term
          </li>
          <li>
            ${phev_min} rebate for short-range PHEV 12-month lease term
          </li>
        </ul>

        <p>This rebate approval will expire one year from today’s date.</p>
        
        <p>Next steps:</p>
        <ol>
          <li>
            Your approval is now linked to your driver’s licence. Bring your driver's licence with you to a new car dealer in B.C.
          </li>
          <li>
            Claim your rebate at the time of vehicle purchase to save money on your new zero-emission vehicle!
          </li>
        </ol>
        <p><i>Please note: This e-mail confirms that you have been approved for a
        rebate under the CleanBC Go Electric Light-Duty Vehicle program only.
        Accessing the rebate is conditional on Program funds being available
        at the time of vehicle purchase.</i></p>

        <p>Questions?</p>

        <p>Please feel free to contact us at ZEVPrograms@gov.bc.ca</p>
        </body>
        </html>
         """.format(
        applicant_full_name=applicant_full_name,
        zev_max=rebate_amounts.ZEV_MAX.value,
        zev_mid=rebate_amounts.ZEV_MID.value,
        zev_min=rebate_amounts.ZEV_MIN.value,
        phev_max=rebate_amounts.PHEV_MAX.value,
        phev_mid=rebate_amounts.PHEV_MID.value,
        phev_min=rebate_amounts.PHEV_MIN.value,
    )
    send_email(
        recipient_email,
        application_id,
        message,
        cc_list=[],
        optional_subject=" – Approved",
    )


def send_not_approve(recipient_email, application_id, tax_year):
    message = """\
        <html>
        <body>

        <p>This email was generated by the CleanBC Go Electric Passenger
        Vehicle Rebate program application.</p>

        <p>Dear Applicant,</p>

        <p>Your application has not been approved.</p>

        <p>Some examples of why this may have happened include:</p>

        <ul>
            <li>
                No record of your {tax_year} Notice of Assessment on file with the Canada Revenue Agency (CRA).
            </li>
            <li>
                The identity records that you have supplied do not match CRA records.
            </li>
            <li>
                Your income does not qualify/exceeds the maximum eligible amount under the program.
            </li>
        </ul>

        <p>Questions?</p>

        <p>Please feel free to contact us at ZEVPrograms@gov.bc.ca</p>
        </body>
        </html>
         """.format(
        tax_year=tax_year
    )
    send_email(
        recipient_email,
        application_id,
        message,
        cc_list=[],
        optional_subject=" – Not Approved",
    )


def send_household_cancel(recipient_email, application_id):
    message = """\
        <html>
        <body>

        <p>This email was generated by the CleanBC Go Electric Passenger
        Vehicle Rebate program application.</p>

        <p>Your application has been cancelled.</p>

        <p>Some examples of why this may have happened include:</p>

        <ul>
            <li>
                The person you identified as your spouse cancelled the application.
            </li>
            <li>
                The person you identified as your spouse didn’t complete the application within 28 days.
            </li>
        </ul>

        <p>You are encouraged to apply again as an individual if your spouse is unable to complete the household application.</p>

        <p>Questions?</p>

        <p>Please feel free to contact us at ZEVPrograms@gov.bc.ca</p>
        </body>
        </html>
         """
    send_email(
        recipient_email,
        application_id,
        message,
        cc_list=[],
        optional_subject=" – Cancelled",
    )


def send_cancel(recipient_email, application_id):
    message = """\
        <html>
        <body>

        <p>This email was generated by the CleanBC Go Electric Passenger
        Vehicle Rebate program application.</p>

        <p>Your application has been cancelled.</p>

        <p>If you haven’t yet received a rebate you are encouraged to apply again.</p>

        <p>If you think this was done in error or you have questions, please feel free to contact us at ZEVPrograms@gov.bc.ca</p>
        
        </body>
        </html>
         """
    send_email(
        recipient_email,
        application_id,
        message,
        cc_list=[],
        optional_subject=" – Cancelled",
    )


def send_expired(recipient_email, application_id):
    message = """\
        <html>
        <body>

        <p>This email was generated by the CleanBC Go Electric Passenger
        Vehicle Rebate program application.</p>

        <p>You are receiving this email as it has been one year since you were approved for a Passenger Vehicle Rebate. 
        Your rebate approval has expired.</p>

        <p>You can reapply for another rebate approval 15 days from today. If you want to reapply within the next 15 days, please contact ZEVPrograms@gov.bc.ca</p>

        <p>https://goelectricbc.gov.bc.ca/</p>

        <p>Please note that rebates are available until the program funds are exhausted.</p>

        <p>Questions?</p>

        <p>Please feel free to contact us at ZEVPrograms@gov.bc.ca</p>
        </body>
        </html>
         """
    send_email(
        recipient_email,
        application_id,
        message,
        cc_list=[],
        optional_subject=" – Expired",
    )


def send_expiry_warning(recipient_email, application_id):
    message = """\
        <html>
        <body>

        <p>This email was generated by the CleanBC Go Electric Passenger
        Vehicle Rebate program application.</p>

        <p>You are receiving this email as it has nearly been one year since you were approved for a Passenger Vehicle Rebate. Your rebate approval will expire in 2 weeks.</p>

        <p>If you do not purchase an EV and receive a rebate within the next 2 weeks, you will need to apply for a new rebate approval on the program website:</p>

        <p>https://goelectricbc.gov.bc.ca/</p>

        <p>Please note that rebates are available until the program funds are exhausted.</p>

        <p>Questions?</p>

        <p>Please feel free to contact us at ZEVPrograms@gov.bc.ca</p>
        </body>
        </html>
         """
    send_email(
        recipient_email,
        application_id,
        message,
        cc_list=[],
        optional_subject=" – Will expire in 2 weeks",
    )


def send_rebates_to_ncda(max_number_of_rebates=100):
    def inner():
        rebates = GoElectricRebate.objects.filter(ncda_id__isnull=True)[
            :max_number_of_rebates
        ]
        for rebate in rebates:
            try:
                ncda_data = notify(
                    rebate.drivers_licence,
                    rebate.last_name,
                    rebate.expiry_date.strftime("%m/%d/%Y"),
                    str(rebate.rebate_max_amount),
                    rebate.application.id if rebate.application else None,
                )
                ncda_id = ncda_data["d"]["ID"]
                GoElectricRebate.objects.filter(id=rebate.id).update(
                    ncda_id=ncda_id, modified=timezone.now()
                )
                application = rebate.application
                if application and (
                    application.status == GoElectricRebateApplication.Status.APPROVED
                ):
                    if rebate.rebate_max_amount == 4000:
                        rebate_amounts = FOUR_THOUSAND_REBATE
                    elif rebate.rebate_max_amount == 2000:
                        rebate_amounts = TWO_THOUSAND_REBATE
                    else:
                        rebate_amounts = ONE_THOUSAND_REBATE
                    async_task(
                        "api.tasks.send_approve",
                        application.email,
                        application.id,
                        get_applicant_full_name(application),
                        rebate_amounts,
                    )
            except Exception:
                print("error posting go_electric_rebate with id %s to ncda" % rebate.id)

    try:
        func_timeout(900, inner)
    except FunctionTimedOut:
        print("send_rebates_to_ncda timed out")
        raise Exception


# check for newly redeemed rebates
def check_rebates_redeemed_since(iso_ts):
    @transaction.atomic
    def inner():
        transformed_time = datetime.strptime(iso_ts, "%Y-%m-%dT%H:%M:%SZ") - timedelta(
            days=1
        )
        ts = transformed_time.strftime("%Y-%m-%dT00:00:00Z")
        print("check_rebate_status " + ts)
        ncda_ids = []
        get_rebates_redeemed_since(ts, ncda_ids, None)
        print(ncda_ids)
        redeemed_rebates = GoElectricRebate.objects.filter(ncda_id__in=ncda_ids)
        redeemed_rebates.update(redeemed=True, modified=timezone.now())
        GoElectricRebateApplication.objects.filter(
            pk__in=list(redeemed_rebates.values_list("application_id", flat=True))
        ).update(
            status=GoElectricRebateApplication.Status.REDEEMED,
            modified=timezone.now(),
        )

    try:
        func_timeout(900, inner)
    except FunctionTimedOut:
        print("check_rebates_redeemed_since job timed out")
        raise Exception


def expire_expired_applications(max_number_of_rebates=50, days_offset=15):
    expired_application_ids = []

    @transaction.atomic
    def expire_rebate(rebate):
        ncda_id = rebate.ncda_id
        ncda_rebates = get_rebate(ncda_id, ["Status"])
        if len(ncda_rebates) == 1 and ncda_rebates[0]["Status"] == "Not-Redeemed":
            application = rebate.application
            if application:
                application.status = GoElectricRebateApplication.Status.EXPIRED
                application.save(update_fields=["status", "modified"])
                rebate.delete()
                delete_rebate(ncda_id)
                try:
                    expired_application_ids.append(application.id)
                except Exception:
                    pass

    def inner():
        threshold = timezone.now().date() - timedelta(days=days_offset)
        expired_rebates = (
            GoElectricRebate.objects.filter(redeemed=False)
            .filter(expiry_date__lte=threshold)
            .filter(ncda_id__isnull=False)
            .filter(application__status=GoElectricRebateApplication.Status.APPROVED)
        )[:max_number_of_rebates]

        for rebate in expired_rebates:
            try:
                expire_rebate(rebate)
            except Exception:
                print("error expiring go_electric_rebate with id %s" % rebate.id)

        print("expired applications: %s" % expired_application_ids)

    try:
        func_timeout(900, inner)
    except FunctionTimedOut:
        print("expire applications job timed out")
        raise Exception


def send_expiry_emails(days_offset=14):
    def inner():
        expiry_email_application_ids = []
        warning_email_application_ids = []
        now_date = timezone.now().date()
        future_date = now_date + timedelta(days=days_offset)
        rebates = (
            GoElectricRebate.objects.filter(redeemed=False)
            .filter(Q(expiry_date__exact=now_date) | Q(expiry_date__exact=future_date))
            .filter(application__status=GoElectricRebateApplication.Status.APPROVED)
        )
        for rebate in rebates:
            application = rebate.application
            expiry_date = rebate.expiry_date
            if application:
                if expiry_date == now_date:
                    async_task(
                        "api.tasks.send_expired",
                        application.email,
                        application.id,
                    )
                    expiry_email_application_ids.append(application.id)
                elif expiry_date == future_date:
                    async_task(
                        "api.tasks.send_expiry_warning",
                        application.email,
                        application.id,
                    )
                    warning_email_application_ids.append(application.id)
        print("expiry emails sent for: %s" % expiry_email_application_ids)
        print("warning emails sent for: %s" % warning_email_application_ids)

    try:
        func_timeout(900, inner)
    except FunctionTimedOut:
        print("sending expiry emails job timed out")
        raise Exception
