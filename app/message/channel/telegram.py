from threading import Event, Lock
from urllib.parse import urlencode
from app.helper.thread_helper import ThreadHelper
import requests

import log
from config import Config
from app.message.channel.channel import IMessageChannel
from app.utils.commons import singleton
from app.utils import RequestUtils

lock = Lock()
WEBHOOK_STATUS = False


@singleton
class Telegram(IMessageChannel):
    __telegram_token = None
    __telegram_chat_id = None
    __webhook_url = None
    __telegram_user_ids = []
    __domain = None
    __config = None
    __message_proxy_event = None

    def __init__(self):
        self.init_config()

    def init_config(self):
        self.__config = Config()
        app = self.__config.get_config('app')
        if app:
            self.__domain = app.get('domain')
            if self.__domain:
                if not self.__domain.startswith('http'):
                    self.__domain = "http://" + self.__domain
                if not self.__domain.endswith('/'):
                    self.__domain = self.__domain + "/"
        message = self.__config.get_config('message')
        if message:
            self.__telegram_token = message.get('telegram', {}).get('telegram_token')
            self.__telegram_chat_id = message.get('telegram', {}).get('telegram_chat_id')
            telegram_user_ids = message.get('telegram', {}).get('telegram_user_ids')
            if telegram_user_ids:
                self.__telegram_user_ids = telegram_user_ids.split(",")
            else:
                self.__telegram_user_ids = []
            if self.__telegram_token \
                    and self.__telegram_chat_id:
                if message.get('telegram', {}).get('webhook'):
                    if self.__domain:
                        self.__webhook_url = "%stelegram" % self.__domain
                        self.__set_bot_webhook()
                    if self.__message_proxy_event:
                        self.__message_proxy_event.set()
                        self.__message_proxy_event = None
                else:
                    self.__del_bot_webhook()
                    if not self.__message_proxy_event:
                        event = Event()
                        self.__message_proxy_event = event
                        ThreadHelper().start_thread(self.__start_telegram_message_proxy, [event])

    def get_status(self):
        """
        ???????????????
        """
        flag, msg = self.send_msg("??????", "????????????????????????")
        if not flag:
            log.error("???Telegram????????????????????????%s" % msg)
        return flag

    def get_admin_user(self):
        """
        ??????Telegram??????????????????ChatId?????????????????????ID
        """
        return str(self.__telegram_chat_id)

    def send_msg(self, title, text="", image="", url="", user_id=""):
        """
        ??????Telegram??????
        :param title: ????????????
        :param text: ????????????
        :param image: ??????????????????
        :param url: ?????????????????????URL
        :param user_id: ??????ID????????????????????????????????????
        :user_id: ???????????????????????????ID???????????????????????????
        """
        if not title and not text:
            return False, "?????????????????????????????????"
        try:
            if not self.__telegram_token or not self.__telegram_chat_id:
                return False, "???????????????"

            if text:
                caption = "<b>%s</b>\n%s" % (title, text.replace("\n\n", "\n"))
            else:
                caption = title
            if image and url:
                caption = "%s\n\n<a href='%s'>????????????</a>" % (caption, url)
            if user_id:
                chat_id = user_id
            else:
                chat_id = self.__telegram_chat_id
            if image:
                # ??????????????????
                values = {"chat_id": chat_id, "photo": image, "caption": caption, "parse_mode": "HTML"}
                sc_url = "https://api.telegram.org/bot%s/sendPhoto?" % self.__telegram_token
            else:
                # ????????????
                values = {"chat_id": chat_id, "text": caption, "parse_mode": "HTML"}
                sc_url = "https://api.telegram.org/bot%s/sendMessage?" % self.__telegram_token
            return self.__send_request(sc_url, values)

        except Exception as msg_e:
            return False, str(msg_e)

    def send_list_msg(self, title, medias: list, user_id=""):
        """
        ?????????????????????
        """
        try:
            if not self.__telegram_token or not self.__telegram_chat_id:
                return False, "???????????????"
            if not title or not isinstance(medias, list):
                return False, "????????????"
            index, image, caption = 1, "", "<b>%s</b>" % title
            for media in medias:
                if not image:
                    image = media.get_message_image()
                caption = "%s\n%s. %s" % (caption, index, media.get_title_vote_string())
                index += 1

            if user_id:
                chat_id = user_id
            else:
                chat_id = self.__telegram_chat_id

            # ??????????????????
            values = {"chat_id": chat_id, "photo": image, "caption": caption, "parse_mode": "HTML"}
            sc_url = "https://api.telegram.org/bot%s/sendPhoto?" % self.__telegram_token
            return self.__send_request(sc_url, values)

        except Exception as msg_e:
            return False, str(msg_e)

    def __send_request(self, sc_url, values):
        """
        ???Telegram????????????
        """
        res = RequestUtils(proxies=self.__config.get_proxies()).get_res(sc_url + urlencode(values))
        if res:
            ret_json = res.json()
            status = ret_json.get("ok")
            if status:
                return True, ""
            else:
                return False, ret_json.get("description")
        else:
            return False, "????????????????????????"

    def __set_bot_webhook(self):
        """
        ??????Telegram Webhook
        """
        if not self.__webhook_url:
            return

        try:
            lock.acquire()
            global WEBHOOK_STATUS
            if not WEBHOOK_STATUS:
                WEBHOOK_STATUS = True
            else:
                return
        finally:
            lock.release()

        status = self.__get_bot_webhook()
        if status and status != 1:
            if status == 2:
                self.__del_bot_webhook()
            values = {"url": self.__webhook_url, "allowed_updates": ["message"]}
            sc_url = "https://api.telegram.org/bot%s/setWebhook?" % self.__telegram_token
            res = RequestUtils(proxies=self.__config.get_proxies()).get_res(sc_url + urlencode(values))
            if res:
                json = res.json()
                if json.get("ok"):
                    log.info("???Telegram???Webhook ???????????????????????????%s" % self.__webhook_url)
                else:
                    log.error("???Telegram???Webhook ???????????????" % json.get("description"))
            else:
                log.error("???Telegram???Webhook ????????????????????????????????????")

    def __get_bot_webhook(self):
        """
        ??????Telegram????????????Webhook
        :return: ?????????1-??????????????????2-??????????????????3-????????????0-????????????
        """
        sc_url = "https://api.telegram.org/bot%s/getWebhookInfo" % self.__telegram_token
        res = RequestUtils(proxies=self.__config.get_proxies()).get_res(sc_url)
        if res and res.json():
            if res.json().get("ok"):
                result = res.json().get("result") or {}
                webhook_url = result.get("url") or ""
                if webhook_url:
                    log.info("???Telegram???Webhook ????????????%s" % webhook_url)
                pending_update_count = result.get("pending_update_count")
                last_error_message = result.get("last_error_message")
                if pending_update_count and last_error_message:
                    log.warn("???Telegram???Webhook ??? %s ????????????????????????????????????????????????%s" % (pending_update_count, last_error_message))
                if webhook_url == self.__webhook_url:
                    return 1
                else:
                    return 2
            else:
                return 3
        else:
            return 0

    def __del_bot_webhook(self):
        """
        ??????Telegram Webhook
        :return: ????????????
        """
        sc_url = "https://api.telegram.org/bot%s/deleteWebhook" % self.__telegram_token
        res = RequestUtils(proxies=self.__config.get_proxies()).get_res(sc_url)
        if res and res.json() and res.json().get("ok"):
            return True
        else:
            return False

    def get_users(self):
        """
        ??????Telegram??????????????????User Ids??????????????????telegram????????????user_id??????
        """
        return self.__telegram_user_ids

    @staticmethod
    def __start_telegram_message_proxy(event: Event):
        log.info("???Telegram???????????????????????????")

        long_poll_timeout = 5

        def consume_messages(_config, _offset, _sc_url, _ds_url):
            try:
                values = {"timeout": long_poll_timeout, "offset": _offset}
                res = RequestUtils(proxies=_config.get_proxies()).get_res(_sc_url + urlencode(values))
                if res and res.json():
                    for msg in res.json().get("result", []):
                        # ????????????????????????????????????offset????????????????????????????????????
                        _offset = msg["update_id"] + 1
                        log.info("???Telegram??????????????????: %s" % msg)
                        local_res = requests.post(_ds_url, json=msg, timeout=10)
                        log.debug("???Telegram???message: %s processed, response is: %s" % (msg, local_res.text))
            except Exception as e:
                log.error("???Telegram???????????????????????????: %s" % e)
            return _offset

        offset = 0
        while True:
            # read config from config.yaml directly to make config.yaml changes aware 
            config = Config()
            message = config.get_config("message")
            channel = message.get("msg_channel")
            telegram_token = message.get('telegram', {}).get('telegram_token')
            web_port = config.get_config("app").get("web_port")
            sc_url = "https://api.telegram.org/bot%s/getUpdates?" % telegram_token
            ds_url = "http://127.0.0.1:%s/telegram" % web_port
            telegram_webhook = message.get('telegram', {}).get('webhook')
            if not channel == "telegram" or not telegram_token or telegram_webhook:
                log.info("???Telegram??????????????????????????????")
                break

            i = 0
            while i < 20 and not event.is_set():
                offset = consume_messages(config, offset, sc_url, ds_url)
                i = i + 1
