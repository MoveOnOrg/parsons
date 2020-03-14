import smtplib

from parsons.notifications.sendmail import SendMail
from parsons.utilities.check_env import check


class SMTP(SendMail):
    """Create a SMTP object, for sending emails.

    `Args:`
        host: str
            The host of the SMTP server
        port: int
            The port of the SMTP server (Default is 587 for TLS)
        username: str
            The username of the SMTP server login
        password: str
            The password of the SMTP server login
        tls: bool
            Defaults to True -- pass "0" or "False" to SMTP_TLS to disable
        close_manually: bool
            When set to True, send_message will not close the connection
    """
    def __init__(self, host=None, port=None, username=None, password=None, tls=None,
                 close_manually=False):
        self.host = check('SMTP_HOST', host)
        self.port = check('SMTP_PORT', port, optional=True) or 587
        self.username = check('SMTP_USER', username)
        self.password = check('SMTP_PASSWORD', password)
        self.tls = not (check('SMTP_TLS', tls, optional=True) in ('false', 'False', '0', False))
        self.close_manually = close_manually

        self.conn = None

    def get_connection(self):
        if self.conn is None:
            self.conn = smtplib.SMTP(self.host, self.port)
            self.conn.ehlo()
            if self.tls:
                self.conn.starttls()
            self.conn.login(self.username, self.password)
        return self.conn

    def _prepare_message(self, message, message_type):
        return message

    def send_message(self, message, user_id=None):
        """Send an email message.

        `Args:`
            message: `MIME object <https://docs.python.org/2/library/email.mime.html>`
                i.e. the objects created by the create_* instance methods
            user_id: NA
                Allows compatibility with Gmail notifier.
        `Returns:`
            dict of refused To addresses (otherwise None)
        """
        conn = self.get_connection()
        result = conn.sendmail(message['From'],
                               [x.strip() for x in message['To'].split(',')],
                               message.as_string())
        if not self.close_manually:
            conn.quit()
            self.conn = None
        return result