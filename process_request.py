import logging

from configuration_bot import BotConfig

from forms import report_form

import pyrustools.bot
import pyrustools.client_plus
import pyrustools.comments_copy
import pyrustools.object_methods
import pyrustools.objects_plus


logging.basicConfig(level=logging.DEBUG)
logging.getLogger('urllib3').propagate = False
logger = logging.getLogger(__name__)


def process_thread(*args):
    """:return."""
    try:
        bot = pyrustools.bot.Bot()
        if len(args) == 1:
            bot.init_from_test('config.json', args[0])
        else:
            bot.init_from_webhook(args[0], args[1], args[2])
        configuration = BotConfig(bot.configuration)
        bot.pyrus_client.update_task_field_info(bot.task)
        bot_form_id = bot.task.form_id
        bot.pyrus_client.comment_task_plus(
            bot.task.id, approval_choice='approved'
        )
        if bot_form_id in configuration.allow_form_ids:
            report_form.process_reports(
                bot.pyrus_client, configuration, bot.task
            )
    except Exception:
        error = pyrustools.object_methods.get_exception()
        logger.error(error)


def process_webhook(body, retry, session_id):
    """

    This function is called from flask app.py.
    Here we're initializing bot parameters, pyrus_client and launching
    in a thread main bot function
    :param body: Body we got from webhook request
    :param retry: Retry number
    :param session_id: Unique session ID
    :return:
    """
    # Running main function in a thread
    pyrustools.bot.start_in_thread(process_thread, body, retry, session_id)
    # Immediately sending 200 OK to Pyrus
    msg = "Sending 200 OK to Pyrus request after launching bot in a thread"
    logger.debug(msg)
    return ''
