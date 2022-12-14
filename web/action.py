import base64
import datetime
import importlib
import json
import os.path
import re
import shutil
import signal

from flask_login import logout_user
from werkzeug.security import generate_password_hash

import cn2an
import log
from app.doubansync import DoubanSync
from app.helper.words_helper import WordsHelper
from app.indexer import BuiltinIndexer
from app.media.douban import DouBan
from app.mediaserver import MediaServer
from app.rsschecker import RssChecker
from app.utils import StringUtils, Torrent, EpisodeFormat, RequestUtils, PathUtils, SystemUtils
from app.helper import ProgressHelper, ThreadHelper, MetaHelper
from app.utils.types import RMT_MODES
from config import RMT_MEDIAEXT, Config, TMDB_IMAGE_W500_URL, TMDB_IMAGE_ORIGINAL_URL
from app.message import Telegram, WeChat, Message, MessageCenter
from app.brushtask import BrushTask
from app.downloader import Qbittorrent, Transmission, Downloader
from app.filterrules import FilterRule
from app.mediaserver import Emby, Jellyfin, Plex
from app.rss import Rss
from app.sites import Sites
from app.subtitle import Subtitle
from app.media import Category, Media, MetaInfo
from app.media.doubanv2api import DoubanApi
from app.filetransfer import FileTransfer
from app.scheduler import restart_scheduler, stop_scheduler
from app.sync import restart_monitor, stop_monitor
from app.scheduler import Scheduler
from app.sync import Sync
from app.utils.types import SearchType, DownloaderType, SyncType, MediaType, SystemDictType
from web.backend.search_torrents import search_medias_for_web, search_media_by_message
from app.subscribe import Subscribe
from app.helper import SqlHelper, DictHelper


class WebAction:
    config = None
    _actions = {}

    def __init__(self):
        self.config = Config()
        self._actions = {
            "sch": self.__sch,
            "search": self.__search,
            "download": self.__download,
            "download_link": self.__download_link,
            "pt_start": self.__pt_start,
            "pt_stop": self.__pt_stop,
            "pt_remove": self.__pt_remove,
            "pt_info": self.__pt_info,
            "del_unknown_path": self.__del_unknown_path,
            "rename": self.__rename,
            "rename_udf": self.__rename_udf,
            "delete_history": self.__delete_history,
            "logging": self.__logging,
            "version": self.__version,
            "update_site": self.__update_site,
            "get_site": self.__get_site,
            "del_site": self.__del_site,
            "restart": self.__restart,
            "update_system": self.__update_system,
            "logout": self.__logout,
            "update_config": self.__update_config,
            "update_directory": self.__update_directory,
            "remove_rss_media": self.__remove_rss_media,
            "add_rss_media": self.__add_rss_media,
            "re_identification": self.__re_identification,
            "media_info": self.__media_info,
            "test_connection": self.__test_connection,
            "user_manager": self.__user_manager,
            "refresh_rss": self.__refresh_rss,
            "refresh_message": self.__refresh_message,
            "delete_tmdb_cache": self.__delete_tmdb_cache,
            "movie_calendar_data": self.__movie_calendar_data,
            "tv_calendar_data": self.__tv_calendar_data,
            "modify_tmdb_cache": self.__modify_tmdb_cache,
            "rss_detail": self.__rss_detail,
            "truncate_blacklist": self.__truncate_blacklist,
            "truncate_rsshistory": self.__truncate_rsshistory,
            "add_brushtask": self.__add_brushtask,
            "del_brushtask": self.__del_brushtask,
            "brushtask_detail": self.__brushtask_detail,
            "add_downloader": self.__add_downloader,
            "delete_downloader": self.__delete_downloader,
            "get_downloader": self.__get_downloader,
            "name_test": self.__name_test,
            "rule_test": self.__rule_test,
            "net_test": self.__net_test,
            "add_filtergroup": self.__add_filtergroup,
            "restore_filtergroup": self.__restore_filtergroup,
            "set_default_filtergroup": self.__set_default_filtergroup,
            "del_filtergroup": self.__del_filtergroup,
            "add_filterrule": self.__add_filterrule,
            "del_filterrule": self.__del_filterrule,
            "filterrule_detail": self.__filterrule_detail,
            "get_site_activity": self.__get_site_activity,
            "get_site_history": self.__get_site_history,
            "get_recommend": self.get_recommend,
            "get_downloaded": self.get_downloaded,
            "get_site_seeding_info": self.__get_site_seeding_info,
            "clear_tmdb_cache": self.__clear_tmdb_cache,
            "check_site_attr": self.__check_site_attr,
            "refresh_process": self.__refresh_process,
            "restory_backup": self.__restory_backup,
            "start_mediasync": self.__start_mediasync,
            "mediasync_state": self.__mediasync_state,
            "get_tvseason_list": self.__get_tvseason_list,
            "get_userrss_task": self.__get_userrss_task,
            "delete_userrss_task": self.__delete_userrss_task,
            "update_userrss_task": self.__update_userrss_task,
            "get_rssparser": self.__get_rssparser,
            "delete_rssparser": self.__delete_rssparser,
            "update_rssparser": self.__update_rssparser,
            "run_userrss": self.__run_userrss,
            "run_brushtask": self.__run_brushtask,
            "list_site_resources": self.__list_site_resources,
            "list_rss_articles": self.__list_rss_articles,
            "rss_article_test": self.__rss_article_test,
            "list_rss_history": self.__list_rss_history,
            "rss_articles_check": self.__rss_articles_check,
            "rss_articles_download": self.__rss_articles_download,
            "add_custom_word_group": self.__add_custom_word_group,
            "delete_custom_word_group": self.__delete_custom_word_group,
            "add_or_edit_custom_word": self.__add_or_edit_custom_word,
            "get_custom_word": self.__get_custom_word,
            "delete_custom_word": self.__delete_custom_word,
            "check_custom_words": self.__check_custom_words,
            "export_custom_words": self.__export_custom_words,
            "analyse_import_custom_words_code": self.__analyse_import_custom_words_code,
            "import_custom_words": self.__import_custom_words,
            "get_categories": self.__get_categories,
            "re_rss_history": self.__re_rss_history,
            "delete_rss_history": self.__delete_rss_history,
            "share_filtergroup": self.__share_filtergroup,
            "import_filtergroup": self.__import_filtergroup
        }

    def action(self, cmd, data):
        func = self._actions.get(cmd)
        if not func:
            return "??????????????????"
        else:
            return func(data)

    @staticmethod
    def shutdown_server():
        """
        ????????????
        """
        # ??????????????????
        stop_scheduler()
        # ????????????
        stop_monitor()
        # ??????
        logout_user()
        # ??????????????????
        os.system("ps -ef|grep -w 'Xvfb'|grep -v grep|awk '{print $1}'|xargs kill -9")
        # ?????????
        os.kill(os.getpid(), getattr(signal, "SIGKILL", signal.SIGTERM))

    @staticmethod
    def handle_message_job(msg, in_from=SearchType.OT, user_id=None):
        """
        ??????????????????
        """
        if not msg:
            return
        commands = {
            "/ptr": {"func": Downloader().remove_torrents, "desp": "??????"},
            "/ptt": {"func": Downloader().transfer, "desp": "??????????????????"},
            "/pts": {"func": Sites().signin, "desp": "????????????"},
            "/rst": {"func": Sync().transfer_all_sync, "desp": "????????????"},
            "/rss": {"func": Rss().rssdownload, "desp": "RSS??????"},
            "/db": {"func": DoubanSync().sync, "desp": "????????????"}
        }
        command = commands.get(msg)
        if command:
            # ??????????????????
            if in_from == SearchType.TG and user_id:
                if str(user_id) != Telegram().get_admin_user():
                    Message().send_channel_msg(channel=in_from, title="??????????????????????????????????????????", user_id=user_id)
                    return
            # ????????????
            ThreadHelper().start_thread(command.get("func"), ())
            Message().send_channel_msg(channel=in_from, title="???????????? %s ..." % command.get("desp"))
        else:
            # ??????????????????
            if in_from == SearchType.TG and user_id:
                if not str(user_id) in Telegram().get_users() \
                        and str(user_id) != Telegram().get_admin_user():
                    Message().send_channel_msg(channel=in_from, title="??????????????????????????????????????????????????????", user_id=user_id)
                    return
            # ??????????????????????????????
            ThreadHelper().start_thread(search_media_by_message, (msg, in_from, user_id,))

    @staticmethod
    def set_config_value(cfg, cfg_key, cfg_value):
        """
        ??????Key???????????????
        """
        # ??????
        if cfg_key == "app.login_password":
            if cfg_value and not cfg_value.startswith("[hash]"):
                cfg['app']['login_password'] = "[hash]%s" % generate_password_hash(cfg_value)
            else:
                cfg['app']['login_password'] = cfg_value or "password"
            return cfg
        # ??????
        if cfg_key == "app.proxies":
            if cfg_value:
                if not cfg_value.startswith("http") and not cfg_value.startswith("sock"):
                    cfg['app']['proxies'] = {"https": "http://%s" % cfg_value, "http": "http://%s" % cfg_value}
                else:
                    cfg['app']['proxies'] = {"https": "%s" % cfg_value, "http": "%s" % cfg_value}
            else:
                cfg['app']['proxies'] = {"https": None, "http": None}
            return cfg
        # ??????????????????
        if cfg_key == "douban.users":
            vals = cfg_value.split(",")
            cfg['douban']['users'] = vals
            return cfg
        # ?????????
        if cfg_key == "jackett.indexers":
            vals = cfg_value.split("\n")
            cfg['jackett']['indexers'] = vals
            return cfg
        # ????????????????????????
        keys = cfg_key.split(".")
        if keys:
            if len(keys) == 1:
                cfg[keys[0]] = cfg_value
            elif len(keys) == 2:
                if not cfg.get(keys[0]):
                    cfg[keys[0]] = {}
                cfg[keys[0]][keys[1]] = cfg_value
            elif len(keys) == 3:
                if cfg.get(keys[0]):
                    if not cfg[keys[0]].get(keys[1]) or isinstance(cfg[keys[0]][keys[1]], str):
                        cfg[keys[0]][keys[1]] = {}
                    cfg[keys[0]][keys[1]][keys[2]] = cfg_value
                else:
                    cfg[keys[0]] = {}
                    cfg[keys[0]][keys[1]] = {}
                    cfg[keys[0]][keys[1]][keys[2]] = cfg_value

        return cfg

    @staticmethod
    def set_config_directory(cfg, oper, cfg_key, cfg_value, update_value=None):
        """
        ??????????????????
        """

        def remove_sync_path(obj, key):
            if not isinstance(obj, list):
                return []
            ret_obj = []
            for item in obj:
                if item.split("@")[0].replace("\\", "/") != key.split("@")[0].replace("\\", "/"):
                    ret_obj.append(item)
            return ret_obj

        # ????????????????????????
        keys = cfg_key.split(".")
        if keys:
            if len(keys) == 1:
                if cfg.get(keys[0]):
                    if not isinstance(cfg[keys[0]], list):
                        cfg[keys[0]] = [cfg[keys[0]]]
                    if oper == "add":
                        cfg[keys[0]].append(cfg_value)
                    elif oper == "sub":
                        cfg[keys[0]].remove(cfg_value)
                        if not cfg[keys[0]]:
                            cfg[keys[0]] = None
                    elif oper == "set":
                        cfg[keys[0]].remove(cfg_value)
                        if update_value:
                            cfg[keys[0]].append(update_value)
                else:
                    cfg[keys[0]] = cfg_value
            elif len(keys) == 2:
                if cfg.get(keys[0]):
                    if not cfg[keys[0]].get(keys[1]):
                        cfg[keys[0]][keys[1]] = []
                    if not isinstance(cfg[keys[0]][keys[1]], list):
                        cfg[keys[0]][keys[1]] = [cfg[keys[0]][keys[1]]]
                    if oper == "add":
                        cfg[keys[0]][keys[1]].append(cfg_value.replace("\\", "/"))
                    elif oper == "sub":
                        cfg[keys[0]][keys[1]] = remove_sync_path(cfg[keys[0]][keys[1]], cfg_value)
                        if not cfg[keys[0]][keys[1]]:
                            cfg[keys[0]][keys[1]] = None
                    elif oper == "set":
                        cfg[keys[0]][keys[1]] = remove_sync_path(cfg[keys[0]][keys[1]], cfg_value)
                        if update_value:
                            cfg[keys[0]][keys[1]].append(update_value.replace("\\", "/"))
                else:
                    cfg[keys[0]] = {}
                    cfg[keys[0]][keys[1]] = cfg_value.replace("\\", "/")
        return cfg

    @staticmethod
    def __sch(data):
        """
        ??????????????????
        """
        commands = {
            "autoremovetorrents": Downloader().remove_torrents,
            "pttransfer": Downloader().transfer,
            "ptsignin": Sites().signin,
            "sync": Sync().transfer_all_sync,
            "rssdownload": Rss().rssdownload,
            "douban": DoubanSync().sync,
            "rsssearch_all": Rss().rsssearch_all,
        }
        sch_item = data.get("item")
        if sch_item and commands.get(sch_item):
            ThreadHelper().start_thread(commands.get(sch_item), ())
        return {"retmsg": "???????????????", "item": sch_item}

    @staticmethod
    def __search(data):
        """
        WEB????????????
        """
        search_word = data.get("search_word")
        ident_flag = False if data.get("unident") else True
        filters = data.get("filters")
        tmdbid = data.get("tmdbid")
        media_type = data.get("media_type")
        if media_type:
            if media_type == "??????":
                media_type = MediaType.MOVIE
            else:
                media_type = MediaType.TV
        if search_word:
            ret, ret_msg = search_medias_for_web(content=search_word,
                                                 ident_flag=ident_flag,
                                                 filters=filters,
                                                 tmdbid=tmdbid,
                                                 media_type=media_type)
            if ret != 0:
                return {"code": ret, "msg": ret_msg}
        return {"code": 0}

    @staticmethod
    def __download(data):
        """
        ???WEB????????????
        """
        dl_id = data.get("id")
        dl_dir = data.get("dir")
        results = SqlHelper.get_search_result_by_id(dl_id)
        for res in results:
            media = Media().get_media_info(title=res[8], subtitle=res[9])
            if not media:
                continue
            media.set_torrent_info(enclosure=res[0],
                                   size=res[10],
                                   site=res[14],
                                   page_url=res[17],
                                   upload_volume_factor=float(res[15]),
                                   download_volume_factor=float(res[16]))
            # ????????????
            ret, ret_msg = Downloader().download(media_info=media,
                                                 download_dir=dl_dir)
            if ret:
                # ????????????
                Message().send_download_message(SearchType.WEB, media)
            else:
                return {"retcode": -1, "retmsg": ret_msg}
        return {"retcode": 0, "retmsg": ""}

    @staticmethod
    def __download_link(data):
        site = data.get("site")
        enclosure = data.get("enclosure")
        title = data.get("title")
        description = data.get("description")
        page_url = data.get("page_url")
        size = data.get("size")
        seeders = data.get("seeders")
        uploadvolumefactor = data.get("uploadvolumefactor")
        downloadvolumefactor = data.get("downloadvolumefactor")
        dl_dir = data.get("dl_dir")
        if not title or not enclosure:
            return {"code": -1, "msg": "??????????????????"}
        media = Media().get_media_info(title=title, subtitle=description)
        media.site = site
        media.enclosure = enclosure
        media.page_url = page_url
        media.size = size
        media.upload_volume_factor = float(uploadvolumefactor)
        media.download_volume_factor = float(downloadvolumefactor)
        media.seeders = seeders
        # ????????????
        ret, ret_msg = Downloader().download(media_info=media,
                                             download_dir=dl_dir)
        if ret:
            # ????????????
            Message().send_download_message(SearchType.WEB, media)
            return {"code": 0, "msg": "????????????"}
        else:
            return {"code": 1, "msg": ret_msg or "???????????????????????????????????????????????????"}

    @staticmethod
    def __pt_start(data):
        """
        ????????????
        """
        tid = data.get("id")
        if id:
            Downloader().start_torrents(tid)
        return {"retcode": 0, "id": tid}

    @staticmethod
    def __pt_stop(data):
        """
        ????????????
        """
        tid = data.get("id")
        if id:
            Downloader().stop_torrents(tid)
        return {"retcode": 0, "id": tid}

    @staticmethod
    def __pt_remove(data):
        """
        ????????????
        """
        tid = data.get("id")
        if id:
            Downloader().delete_torrents(tid)
        return {"retcode": 0, "id": tid}

    @staticmethod
    def __pt_info(data):
        """
        ???????????????????????????
        """
        ids = data.get("ids")
        Client, Torrents = Downloader().get_torrents(torrent_ids=ids)
        DispTorrents = []
        for torrent in Torrents:
            if not torrent:
                continue
            if Client == DownloaderType.QB:
                if torrent.get('state') in ['pausedDL']:
                    state = "Stoped"
                    speed = "?????????"
                else:
                    state = "Downloading"
                    dlspeed = StringUtils.str_filesize(torrent.get('dlspeed'))
                    eta = StringUtils.str_timelong(torrent.get('eta'))
                    upspeed = StringUtils.str_filesize(torrent.get('upspeed'))
                    speed = "%s%sB/s %s%sB/s %s" % (chr(8595), dlspeed, chr(8593), upspeed, eta)
                # ??????
                progress = round(torrent.get('progress') * 100)
                # ??????
                key = torrent.get('hash')
            elif Client == DownloaderType.Client115:
                state = "Downloading"
                dlspeed = StringUtils.str_filesize(torrent.get('peers'))
                upspeed = StringUtils.str_filesize(torrent.get('rateDownload'))
                speed = "%s%sB/s %s%sB/s" % (chr(8595), dlspeed, chr(8593), upspeed)
                # ??????
                progress = round(torrent.get('percentDone'), 1)
                # ??????
                key = torrent.get('info_hash')
            elif Client == DownloaderType.Aria2:
                if torrent.get('status') != 'active':
                    state = "Stoped"
                    speed = "?????????"
                else:
                    state = "Downloading"
                    dlspeed = StringUtils.str_filesize(torrent.get('downloadSpeed'))
                    upspeed = StringUtils.str_filesize(torrent.get('uploadSpeed'))
                    speed = "%s%sB/s %s%sB/s" % (chr(8595), dlspeed, chr(8593), upspeed)
                # ??????
                progress = round(int(torrent.get('completedLength')) / int(torrent.get("totalLength")), 1) * 100
                # ??????
                key = torrent.get('gid')
            else:
                if torrent.status in ['stopped']:
                    state = "Stoped"
                    speed = "?????????"
                else:
                    state = "Downloading"
                    dlspeed = StringUtils.str_filesize(torrent.rateDownload)
                    upspeed = StringUtils.str_filesize(torrent.rateUpload)
                    speed = "%s%sB/s %s%sB/s" % (chr(8595), dlspeed, chr(8593), upspeed)
                # ??????
                progress = round(torrent.progress, 1)
                # ??????
                key = torrent.id

            torrent_info = {'id': key, 'speed': speed, 'state': state, 'progress': progress}
            if torrent_info not in DispTorrents:
                DispTorrents.append(torrent_info)
        return {"retcode": 0, "torrents": DispTorrents}

    @staticmethod
    def __del_unknown_path(data):
        """
        ????????????
        """
        tids = data.get("id")
        if isinstance(tids, list):
            for tid in tids:
                if not tid:
                    continue
                SqlHelper.delete_transfer_unknown(tid)
            return {"retcode": 0}
        else:
            retcode = SqlHelper.delete_transfer_unknown(tids)
            return {"retcode": retcode}

    @staticmethod
    def __rename(data):
        """
        ????????????
        """
        path = dest_dir = None
        syncmod = RMT_MODES.get(data.get("syncmod"))
        logid = data.get("logid")
        if logid:
            paths = SqlHelper.get_transfer_path_by_id(logid)
            if paths:
                path = os.path.join(paths[0][0], paths[0][1])
                dest_dir = paths[0][2]
            else:
                return {"retcode": -1, "retmsg": "??????????????????????????????"}
        else:
            unknown_id = data.get("unknown_id")
            if unknown_id:
                paths = SqlHelper.get_unknown_path_by_id(unknown_id)
                if paths:
                    path = paths[0][0]
                    dest_dir = paths[0][1]
                else:
                    return {"retcode": -1, "retmsg": "???????????????????????????"}
        if not dest_dir:
            dest_dir = ""
        if not path:
            return {"retcode": -1, "retmsg": "??????????????????"}
        tmdbid = data.get("tmdb")
        title = data.get("title")
        year = data.get("year")
        mtype = data.get("type")
        season = data.get("season")
        episode_format = data.get("episode_format")
        min_filesize = data.get("min_filesize")
        if mtype == "TV":
            media_type = MediaType.TV
        elif mtype == "MOV":
            media_type = MediaType.MOVIE
        else:
            media_type = MediaType.ANIME
        tmdb_info = Media().get_tmdb_info(media_type, title, year, tmdbid)
        if not tmdb_info:
            return {"retcode": 1, "retmsg": "??????????????????????????????TMDB??????"}
        # ????????????????????????????????????????????????????????????????????????????????????????????????episode_format??????
        need_fix_all = False
        if os.path.splitext(path)[-1].lower() in RMT_MEDIAEXT and episode_format:
            path = os.path.dirname(path)
            need_fix_all = True
        # ???????????????????????????????????????
        Media().save_rename_cache(path, tmdb_info)
        # ????????????
        succ_flag, ret_msg = FileTransfer().transfer_media(in_from=SyncType.MAN,
                                                           in_path=path,
                                                           rmt_mode=syncmod,
                                                           target_dir=dest_dir,
                                                           tmdb_info=tmdb_info,
                                                           media_type=media_type,
                                                           season=season,
                                                           episode=(EpisodeFormat(episode_format), need_fix_all),
                                                           min_filesize=min_filesize)
        if succ_flag:
            if not need_fix_all and not logid:
                SqlHelper.update_transfer_unknown_state(path)
            return {"retcode": 0, "retmsg": "????????????"}
        else:
            return {"retcode": 2, "retmsg": ret_msg}

    @staticmethod
    def __rename_udf(data):
        """
        ???????????????
        """
        inpath = data.get("inpath")
        outpath = data.get("outpath")
        syncmod = RMT_MODES.get(data.get("syncmod"))
        if not os.path.exists(inpath):
            return {"retcode": -1, "retmsg": "?????????????????????"}
        tmdbid = data.get("tmdb")
        if not tmdbid.strip() and not tmdbid.isdigit():
            return {"retcode": -1, "retmsg": "tmdbid ??????????????????"}
        mtype = data.get("type")
        season = data.get("season")
        episode_format = data.get("episode_format")
        episode_details = data.get("episode_details")
        episode_offset = data.get("episode_offset")
        min_filesize = data.get("min_filesize")
        if mtype == "TV":
            media_type = MediaType.TV
        elif mtype == "MOV":
            media_type = MediaType.MOVIE
        else:
            media_type = MediaType.ANIME
        tmdb_info = Media().get_tmdb_info(mtype=media_type, tmdbid=tmdbid)
        if not tmdb_info:
            return {"retcode": 1, "retmsg": "??????????????????????????????TMDB??????"}
        # ???????????????????????????????????????
        Media().save_rename_cache(inpath, tmdb_info)
        # ???????????????
        succ_flag, ret_msg = FileTransfer().transfer_media(in_from=SyncType.MAN,
                                                           in_path=inpath,
                                                           rmt_mode=syncmod,
                                                           target_dir=outpath,
                                                           tmdb_info=tmdb_info,
                                                           media_type=media_type,
                                                           season=season,
                                                           episode=(
                                                               EpisodeFormat(episode_format, episode_details,
                                                                             episode_offset), False),
                                                           min_filesize=min_filesize,
                                                           udf_flag=True)
        if succ_flag:
            return {"retcode": 0, "retmsg": "????????????"}
        else:
            return {"retcode": 2, "retmsg": ret_msg}

    @staticmethod
    def __delete_history(data):
        """
        ???????????????????????????
        """
        logids = data.get('logids')
        for logid in logids:
            # ??????????????????
            paths = SqlHelper.get_transfer_path_by_id(logid)
            if paths:
                dest_dir = paths[0][2]
                meta_info = MetaInfo(title=paths[0][1])
                meta_info.title = paths[0][3]
                meta_info.category = paths[0][4]
                meta_info.year = paths[0][5]
                if paths[0][6]:
                    meta_info.begin_season = int(str(paths[0][6]).replace("S", ""))
                if paths[0][7] == MediaType.MOVIE.value:
                    meta_info.type = MediaType.MOVIE
                else:
                    meta_info.type = MediaType.TV
                # ????????????
                SqlHelper.delete_transfer_log_by_id(logid)
                # ????????????
                dest_path = FileTransfer().get_dest_path_by_info(dest=dest_dir, meta_info=meta_info)
                if dest_path and dest_path.find(meta_info.title) != -1:
                    rm_parent_dir = False
                    if not meta_info.get_season_list():
                        # ???????????????????????????
                        try:
                            shutil.rmtree(dest_path)
                        except Exception as e:
                            log.console(str(e))
                    elif not meta_info.get_episode_string():
                        # ??????????????????????????????????????????
                        try:
                            shutil.rmtree(dest_path)
                        except Exception as e:
                            log.console(str(e))
                        rm_parent_dir = True
                    else:
                        # ???????????????????????????????????????????????????
                        for dest_file in PathUtils.get_dir_files(dest_path):
                            file_meta_info = MetaInfo(os.path.basename(dest_file))
                            if file_meta_info.get_episode_list() and set(
                                    file_meta_info.get_episode_list()).issubset(set(meta_info.get_episode_list())):
                                try:
                                    os.remove(dest_file)
                                except Exception as e:
                                    log.console(str(e))
                        rm_parent_dir = True
                    if rm_parent_dir \
                            and not PathUtils.get_dir_files(os.path.dirname(dest_path), exts=RMT_MEDIAEXT):
                        # ??????????????????????????????????????????
                        try:
                            shutil.rmtree(os.path.dirname(dest_path))
                        except Exception as e:
                            log.console(str(e))
        return {"retcode": 0}

    @staticmethod
    def __logging(data):
        """
        ??????????????????
        """
        if log.LOG_INDEX:
            if log.LOG_INDEX > len(list(log.LOG_QUEUE)):
                text = "<br/>".join(list(log.LOG_QUEUE))
            else:
                text = "<br/>".join(list(log.LOG_QUEUE)[-log.LOG_INDEX:])
            log.LOG_INDEX = 0
            return {"text": text + "<br/>"}
        return {"text": ""}

    def __version(self, data):
        """
        ???????????????
        """
        try:
            response = RequestUtils(proxies=self.config.get_proxies()).get_res(
                "https://api.github.com/repos/jxxghp/nas-tools/releases/latest")
            if response:
                ver_json = response.json()
                version = ver_json["tag_name"]
                info = f'<a href="{ver_json["html_url"]}" target="_blank">{version}</a>'
                return {"code": 0, "version": version, "info": info}
        except Exception as e:
            print(str(e))
        return {"code": -1, "version": "", "info": ""}

    @staticmethod
    def __update_site(data):
        """
        ??????????????????
        """

        def __is_site_duplicate(query_name, query_tid):
            # ??????????????????
            _sites = SqlHelper.get_site_by_name(name=query_name)
            for site in _sites:
                site_id = site[0]
                if str(site_id) != str(query_tid):
                    return True
            return False

        tid = data.get('site_id')
        name = data.get('site_name')
        site_pri = data.get('site_pri')
        rssurl = data.get('site_rssurl')
        signurl = data.get('site_signurl')
        cookie = data.get('site_cookie')
        note = data.get('site_note')
        rss_uses = data.get('site_include')

        if __is_site_duplicate(name, tid):
            return {"code": 400, "msg": "??????????????????"}

        if tid:
            sites = SqlHelper.get_site_by_id(tid)
            # ???????????????
            if not sites:
                return {"code": 400, "msg": "???????????????"}

            old_name = sites[0][1]

            ret = SqlHelper.update_config_site(tid=tid,
                                               name=name,
                                               site_pri=site_pri,
                                               rssurl=rssurl,
                                               signurl=signurl,
                                               cookie=cookie,
                                               note=note,
                                               rss_uses=rss_uses)
            if ret and (name != old_name):
                # ??????????????????????????????
                SqlHelper.update_site_user_statistics_site_name(name, old_name)
                SqlHelper.update_site_seed_info_site_name(name, old_name)
                SqlHelper.update_site_statistics_site_name(name, old_name)

        else:
            ret = SqlHelper.insert_config_site(name=name,
                                               site_pri=site_pri,
                                               rssurl=rssurl,
                                               signurl=signurl,
                                               cookie=cookie,
                                               note=note,
                                               rss_uses=rss_uses)
        # ??????????????????
        Sites().init_config()

        return {"code": ret}

    @staticmethod
    def __get_site(data):
        """
        ????????????????????????
        """
        tid = data.get("id")
        site_free = False
        site_2xfree = False
        site_hr = False
        if tid:
            ret = Sites().get_sites(siteid=tid)
            if ret.get("rssurl"):
                site_attr = Sites().get_grapsite_conf(ret.get("rssurl"))
                if site_attr.get("FREE"):
                    site_free = True
                if site_attr.get("2XFREE"):
                    site_2xfree = True
                if site_attr.get("HR"):
                    site_hr = True
        else:
            ret = []
        return {"code": 0, "site": ret, "site_free": site_free, "site_2xfree": site_2xfree, "site_hr": site_hr}

    @staticmethod
    def __del_site(data):
        """
        ????????????????????????
        """
        tid = data.get("id")
        if tid:
            ret = SqlHelper.delete_config_site(tid)
            Sites().init_config()
            return {"code": ret}
        else:
            return {"code": 0}

    def __restart(self, data):
        """
        ??????
        """
        # ???????????????
        self.shutdown_server()

    def __update_system(self, data):
        """
        ??????
        """
        # ??????
        if "synology" in SystemUtils.execute('uname -a'):
            if SystemUtils.execute('/bin/ps -w -x | grep -v grep | grep -w "nastool update" | wc -l') == '0':
                # ????????????????????????????????????
                os.system('nastool update')
                # ???????????????
                self.shutdown_server()
        else:
            # ????????????
            os.system('pip install -r /nas-tools/requirements.txt')
            # ??????
            os.system("git clean -dffx")
            os.system("git reset --hard HEAD")
            # ??????
            os.system("git pull")
            os.system("git submodule update --init --recursive")
            # ???????????????
            self.shutdown_server()

    @staticmethod
    def __logout(data):
        """
        ??????
        """
        logout_user()
        return {"code": 0}

    def __update_config(self, data):
        """
        ??????????????????
        """
        cfg = self.config.get_config()
        cfgs = dict(data).items()
        # ??????????????????
        config_test = False
        scheduler_reload = False
        emby_reload = False
        jellyfin_reload = False
        plex_reload = False
        wechat_reload = False
        telegram_reload = False
        category_reload = False
        subtitle_reload = False
        sites_reload = False
        # ????????????
        for key, value in cfgs:
            if key == "test" and value:
                config_test = True
                continue
            # ????????????
            cfg = self.set_config_value(cfg, key, value)
            if key in ['pt.ptsignin_cron', 'pt.pt_monitor', 'pt.pt_check_interval', 'pt.pt_seeding_time',
                       'douban.interval', 'media.mediasync_interval']:
                scheduler_reload = True
            if key.startswith("emby"):
                emby_reload = True
            if key.startswith("jellyfin"):
                jellyfin_reload = True
            if key.startswith("plex"):
                plex_reload = True
            if key.startswith("message.telegram"):
                telegram_reload = True
            if key.startswith("message.wechat"):
                wechat_reload = True
            if key.startswith("media.category"):
                category_reload = True
            if key.startswith("subtitle"):
                subtitle_reload = True
            if key.startswith("message.switch"):
                sites_reload = True
        # ????????????
        if not config_test:
            self.config.save_config(cfg)
        # ??????????????????
        if scheduler_reload:
            Scheduler().init_config()
            restart_scheduler()
        # ??????emby
        if emby_reload:
            Emby().init_config()
        # ??????Jellyfin
        if jellyfin_reload:
            Jellyfin().init_config()
        # ??????Plex
        if plex_reload:
            Plex().init_config()
        # ??????wechat
        if wechat_reload:
            WeChat().init_config()
        # ??????telegram
        if telegram_reload:
            Telegram().init_config()
        # ??????????????????
        if category_reload:
            Category().init_config()
        # ????????????
        if subtitle_reload:
            Subtitle().init_config()
        # ????????????
        if sites_reload:
            Sites().init_config()

        return {"code": 0}

    def __update_directory(self, data):
        """
        ?????????????????????
        """
        cfg = self.set_config_directory(self.config.get_config(),
                                        data.get("oper"),
                                        data.get("key"),
                                        data.get("value"),
                                        data.get("replace_value"))
        # ????????????
        self.config.save_config(cfg)
        if data.get("key") == "sync.sync_path":
            # ????????????
            Sync().init_config()
            # ????????????????????????
            restart_monitor()
        return {"code": 0}

    @staticmethod
    def __remove_rss_media(data):
        """
        ??????RSS??????
        """
        name = data.get("name")
        mtype = data.get("type")
        year = data.get("year")
        season = data.get("season")
        rssid = data.get("rssid")
        page = data.get("page")
        tmdbid = data.get("tmdbid")
        if name:
            name = MetaInfo(title=name).get_name()
        if mtype:
            if mtype in ['nm', 'hm', 'dbom', 'dbhm', 'dbnm', 'dbtop', 'MOV', '??????']:
                SqlHelper.delete_rss_movie(title=name, year=year, rssid=rssid, tmdbid=tmdbid)
            else:
                SqlHelper.delete_rss_tv(title=name, season=season, rssid=rssid, tmdbid=tmdbid)
        return {"code": 0, "page": page, "name": name}

    @staticmethod
    def __add_rss_media(data):
        """
        ??????RSS??????
        """
        doubanid = data.get("doubanid")
        tmdbid = data.get("tmdbid")
        name = data.get("name")
        mtype = data.get("type")
        year = data.get("year")
        season = data.get("season")
        match = data.get("match")
        page = data.get("page")
        sites = data.get("sites")
        search_sites = data.get("search_sites")
        over_edition = data.get("over_edition")
        rss_restype = data.get("rss_restype")
        rss_pix = data.get("rss_pix")
        rss_team = data.get("rss_team")
        rss_rule = data.get("rss_rule")
        rssid = data.get("rssid")
        total_ep = data.get("total_ep")
        current_ep = data.get("current_ep")
        if name and mtype:
            if mtype in ['nm', 'hm', 'dbom', 'dbhm', 'dbnm', 'dbtop', 'MOV', '??????']:
                mtype = MediaType.MOVIE
            else:
                mtype = MediaType.TV
        if isinstance(season, list):
            code = 0
            msg = ""
            for sea in season:
                code, msg, media_info = Subscribe.add_rss_subscribe(mtype=mtype,
                                                                    name=name,
                                                                    year=year,
                                                                    season=sea,
                                                                    match=match,
                                                                    doubanid=doubanid,
                                                                    tmdbid=tmdbid,
                                                                    sites=sites,
                                                                    search_sites=search_sites,
                                                                    over_edition=over_edition,
                                                                    rss_restype=rss_restype,
                                                                    rss_pix=rss_pix,
                                                                    rss_team=rss_team,
                                                                    rss_rule=rss_rule,
                                                                    rssid=rssid)
                if code != 0:
                    break
        else:
            code, msg, media_info = Subscribe.add_rss_subscribe(mtype=mtype,
                                                                name=name,
                                                                year=year,
                                                                season=season,
                                                                match=match,
                                                                doubanid=doubanid,
                                                                tmdbid=tmdbid,
                                                                sites=sites,
                                                                search_sites=search_sites,
                                                                over_edition=over_edition,
                                                                rss_restype=rss_restype,
                                                                rss_pix=rss_pix,
                                                                rss_team=rss_team,
                                                                rss_rule=rss_rule,
                                                                rssid=rssid,
                                                                total_ep=total_ep,
                                                                current_ep=current_ep)
        if not rssid:
            if mtype == MediaType.MOVIE:
                rssid = SqlHelper.get_rss_movie_id(title=name, tmdbid=tmdbid or "DB:%s" % doubanid)
            else:
                rssid = SqlHelper.get_rss_tv_id(title=name, tmdbid=tmdbid or "DB:%s" % doubanid)
        return {"code": code, "msg": msg, "page": page, "name": name, "rssid": rssid}

    @staticmethod
    def __re_identification(data):
        """
        ????????????????????????
        """
        flag = data.get("flag")
        ids = data.get("ids")
        ret_flag = True
        ret_msg = ""
        if flag == "unknow":
            for wid in ids:
                paths = SqlHelper.get_unknown_path_by_id(wid)
                if paths:
                    path = paths[0][0]
                    dest_dir = paths[0][1]
                else:
                    return {"retcode": -1, "retmsg": "???????????????????????????"}
                if not dest_dir:
                    dest_dir = ""
                if not path:
                    return {"retcode": -1, "retmsg": "?????????????????????"}
                succ_flag, msg = FileTransfer().transfer_media(in_from=SyncType.MAN,
                                                               in_path=path,
                                                               target_dir=dest_dir)
                if succ_flag:
                    SqlHelper.update_transfer_unknown_state(path)
                else:
                    ret_flag = False
                    ret_msg = "%s\n%s" % (ret_msg, msg)
        elif flag == "history":
            for wid in ids:
                paths = SqlHelper.get_transfer_path_by_id(wid)
                if paths:
                    path = os.path.join(paths[0][0], paths[0][1])
                    dest_dir = paths[0][2]
                else:
                    return {"retcode": -1, "retmsg": "??????????????????????????????"}
                if not dest_dir:
                    dest_dir = ""
                if not path:
                    return {"retcode": -1, "retmsg": "?????????????????????"}
                succ_flag, msg = FileTransfer().transfer_media(in_from=SyncType.MAN,
                                                               in_path=path,
                                                               target_dir=dest_dir)
                if not succ_flag:
                    ret_flag = False
                    ret_msg = "%s\n%s" % (ret_msg, msg)
        if ret_flag:
            return {"retcode": 0, "retmsg": "????????????"}
        else:
            return {"retcode": 2, "retmsg": ret_msg}

    @staticmethod
    def __media_info(data):
        """
        ??????????????????
        """
        tmdbid = data.get("id")
        mtype = data.get("type")
        title = data.get("title")
        year = data.get("year")
        page = data.get("page")
        doubanid = data.get("doubanid")
        rssid = data.get("rssid")
        if mtype in ['hm', 'nm', 'dbom', 'dbhm', 'dbnm', 'dbtop', 'MOV', '??????']:
            media_type = MediaType.MOVIE
        else:
            media_type = MediaType.TV

        if media_type == MediaType.MOVIE:
            # ???????????????
            if doubanid:
                link_url = "https://movie.douban.com/subject/%s" % doubanid
                douban_info = DoubanApi().movie_detail(doubanid)
                if not douban_info or douban_info.get("localized_message"):
                    return {"code": 1, "retmsg": "???????????????????????????", "link_url": link_url, "rssid": rssid}
                overview = douban_info.get("intro")
                poster_path = douban_info.get("cover_url")
                title = douban_info.get("title")
                rating = douban_info.get("rating", {}) or {}
                vote_average = rating.get("value") or ""
                release_date = douban_info.get("pubdate")
                year = douban_info.get("year")
            else:
                link_url = "https://www.themoviedb.org/movie/%s" % tmdbid
                tmdb_info = Media().get_tmdb_info(media_type, title, year, tmdbid)
                if not tmdb_info:
                    return {"code": 1, "retmsg": "???????????????TMDB??????", "link_url": link_url, "rssid": rssid}
                overview = tmdb_info.get("overview")
                poster_path = TMDB_IMAGE_W500_URL % tmdb_info.get('poster_path') if tmdb_info.get(
                    'poster_path') else ""
                title = tmdb_info.get('title')
                vote_average = round(float(tmdb_info.get("vote_average")), 1)
                release_date = tmdb_info.get('release_date')
                year = release_date[0:4] if release_date else ""

            # ???????????????
            if not rssid:
                rssid = SqlHelper.get_rss_movie_id(title=title, tmdbid=tmdbid or "DB:%s" % doubanid)

            # ???????????????

            return {
                "code": 0,
                "type": mtype,
                "type_str": media_type.value,
                "page": page,
                "title": title,
                "vote_average": vote_average,
                "poster_path": poster_path,
                "release_date": release_date,
                "year": year,
                "overview": overview,
                "link_url": link_url,
                "tmdbid": tmdbid,
                "doubanid": doubanid,
                "rssid": rssid,
                "seasons": []
            }
        else:
            # ???????????????
            if doubanid:
                link_url = "https://movie.douban.com/subject/%s" % doubanid
                douban_info = DoubanApi().tv_detail(doubanid)
                if not douban_info or douban_info.get("localized_message"):
                    return {"code": 1, "retmsg": "???????????????????????????", "link_url": link_url, "rssid": rssid}
                overview = douban_info.get("intro")
                poster_path = douban_info.get("cover_url")
                title = douban_info.get("title")
                rating = douban_info.get("rating", {}) or {}
                vote_average = rating.get("value") or ""
                release_date = douban_info.get("pubdate")
                year = douban_info.get("year")
                seasons = []
            else:
                link_url = "https://www.themoviedb.org/tv/%s" % tmdbid
                tmdb_info = Media().get_tmdb_info(media_type, title, year, tmdbid)
                if not tmdb_info:
                    return {"code": 1, "retmsg": "???????????????TMDB??????", "link_url": link_url, "rssid": rssid}
                overview = tmdb_info.get("overview")
                poster_path = TMDB_IMAGE_W500_URL % tmdb_info.get('poster_path') if tmdb_info.get(
                    'poster_path') else ""
                title = tmdb_info.get('name')
                vote_average = round(float(tmdb_info.get("vote_average")), 1)
                release_date = tmdb_info.get('first_air_date')
                year = release_date[0:4] if release_date else ""
                seasons = [{"text": "???%s???" % cn2an.an2cn(season.get("season_number"), mode='low'),
                            "num": season.get("season_number")} for season in
                           Media().get_tmdb_seasons_list(tv_info=tmdb_info)]

            # ???????????????
            if not rssid:
                rssid = SqlHelper.get_rss_tv_id(title=title, tmdbid=tmdbid or "DB:%s" % doubanid)

            return {
                "code": 0,
                "type": mtype,
                "type_str": media_type.value,
                "page": page,
                "title": title,
                "vote_average": vote_average,
                "poster_path": poster_path,
                "release_date": release_date,
                "year": year,
                "overview": overview,
                "link_url": link_url,
                "tmdbid": tmdbid,
                "doubanid": doubanid,
                "rssid": rssid,
                "seasons": seasons
            }

    def __test_connection(self, data):
        """
        ???????????????
        """
        # ????????????????????????????????????????????????????????????????????????xx|xx????????????????????????????????????????????????
        command = data.get("command")
        ret = None
        if command:
            try:
                if isinstance(command, list):
                    for cmd_str in command:
                        ret = eval(cmd_str)
                        if not ret:
                            break
                else:
                    if command.find("|") != -1:
                        module = command.split("|")[0]
                        class_name = command.split("|")[1]
                        ret = getattr(importlib.import_module(module), class_name)().get_status()
                    else:
                        ret = eval(command)
                # ????????????
                self.config.init_config()
            except Exception as e:
                ret = None
                print(str(e))
            return {"code": 0 if ret else 1}
        return {"code": 0}

    @staticmethod
    def __user_manager(data):
        """
        ????????????
        """
        oper = data.get("oper")
        name = data.get("name")
        if oper == "add":
            password = generate_password_hash(str(data.get("password")))
            pris = data.get("pris")
            if isinstance(pris, list):
                pris = ",".join(pris)
            ret = SqlHelper.insert_user(name, password, pris)
        else:
            ret = SqlHelper.delete_user(name)
        return {"code": ret}

    @staticmethod
    def __refresh_rss(data):
        """
        ????????????RSS
        """
        mtype = data.get("type")
        rssid = data.get("rssid")
        page = data.get("page")
        if mtype == "MOV":
            ThreadHelper().start_thread(Rss().rsssearch_movie, (rssid,))
        else:
            ThreadHelper().start_thread(Rss().rsssearch_tv, (rssid,))
        return {"code": 0, "page": page}

    @staticmethod
    def __refresh_message(data):
        """
        ????????????????????????
        """
        lst_time = data.get("lst_time")
        messages = MessageCenter().get_system_messages(lst_time=lst_time)
        message_html = []
        for message in list(reversed(messages)):
            lst_time = message.get("time")
            level = "bg-red" if message.get("level") == "ERROR" else ""
            content = re.sub(r"[#]+", "<br>",
                             re.sub(r"<[^>]+>", "",
                                    re.sub(r"<br/?>", "####", message.get("content"), flags=re.IGNORECASE)))
            message_html.append(f"""
            <div class="list-group-item">
              <div class="row align-items-center">
                <div class="col-auto">
                  <span class="status-dot {level} d-block"></span>
                </div>
                <div class="col text-truncate">
                  <span class="text-wrap">{message.get("title")}</span>
                  <div class="d-block text-muted text-truncate mt-n1 text-wrap">{content}</div>
                  <div class="d-block text-muted text-truncate mt-n1 text-wrap">{message.get("time")}</div>
                </div>
              </div>
            </div>
            """)
        return {"code": 0, "message": message_html, "lst_time": lst_time}

    @staticmethod
    def __delete_tmdb_cache(data):
        """
        ??????tmdb??????
        """
        if MetaHelper().delete_meta_data(data.get("cache_key")):
            MetaHelper().save_meta_data()
        return {"code": 0}

    @staticmethod
    def __movie_calendar_data(data):
        """
        ????????????????????????
        """
        tid = data.get("id")
        if tid and tid.startswith("DB:"):
            doubanid = tid.replace("DB:", "")
            douban_info = DoubanApi().movie_detail(doubanid)
            if not douban_info:
                return {"code": 1, "retmsg": "???????????????????????????"}
            poster_path = douban_info.get("cover_url") or ""
            title = douban_info.get("title")
            rating = douban_info.get("rating", {}) or {}
            vote_average = rating.get("value") or "???"
            release_date = douban_info.get("pubdate")
            if release_date:
                release_date = re.sub(r"\(.*\)", "", douban_info.get("pubdate")[0])
            if not release_date:
                return {"code": 1, "retmsg": "?????????????????????"}
            else:
                return {"code": 0,
                        "type": "??????",
                        "title": title,
                        "start": release_date,
                        "id": tid,
                        "year": release_date[0:4] if release_date else "",
                        "poster": poster_path,
                        "vote_average": vote_average
                        }
        else:
            tmdb_info = Media().get_tmdb_info(mtype=MediaType.MOVIE, tmdbid=tid)
            if not tmdb_info:
                return {"code": 1, "retmsg": "???????????????TMDB??????"}
            poster_path = TMDB_IMAGE_W500_URL % tmdb_info.get('poster_path') if tmdb_info.get(
                'poster_path') else ""
            title = tmdb_info.get('title')
            vote_average = tmdb_info.get("vote_average")
            release_date = tmdb_info.get('release_date')
            if not release_date:
                return {"code": 1, "retmsg": "?????????????????????"}
            else:
                return {"code": 0,
                        "type": "??????",
                        "title": title,
                        "start": release_date,
                        "id": tid,
                        "year": release_date[0:4] if release_date else "",
                        "poster": poster_path,
                        "vote_average": vote_average
                        }

    @staticmethod
    def __tv_calendar_data(data):
        """
        ???????????????????????????
        """
        tid = data.get("id")
        season = data.get("season")
        name = data.get("name")
        if tid and tid.startswith("DB:"):
            doubanid = tid.replace("DB:", "")
            douban_info = DoubanApi().tv_detail(doubanid)
            if not douban_info:
                return {"code": 1, "retmsg": "???????????????????????????"}
            poster_path = douban_info.get("cover_url") or ""
            title = douban_info.get("title")
            rating = douban_info.get("rating", {}) or {}
            vote_average = rating.get("value") or "???"
            release_date = re.sub(r"\(.*\)", "", douban_info.get("pubdate")[0])
            if not release_date:
                return {"code": 1, "retmsg": "?????????????????????"}
            else:
                return {"code": 0,
                        "type": "?????????",
                        "title": title,
                        "start": release_date,
                        "id": tid,
                        "year": release_date[0:4] if release_date else "",
                        "poster": poster_path,
                        "vote_average": vote_average
                        }
        else:
            tmdb_info = Media().get_tmdb_tv_season_detail(tmdbid=tid, season=season)
            if not tmdb_info:
                return {"code": 1, "retmsg": "???????????????TMDB??????"}
            episode_events = []
            air_date = tmdb_info.get("air_date")
            if not tmdb_info.get("poster_path"):
                tv_tmdb_info = Media().get_tmdb_info(mtype=MediaType.TV, tmdbid=tid)
                if tv_tmdb_info:
                    poster_path = TMDB_IMAGE_W500_URL % tv_tmdb_info.get("poster_path")
                else:
                    poster_path = ""
            else:
                poster_path = TMDB_IMAGE_W500_URL % tmdb_info.get("poster_path")
            year = air_date[0:4] if air_date else ""
            for episode in tmdb_info.get("episodes"):
                episode_events.append({
                    "type": "??????",
                    "title": "%s ???%s??????%s???" % (
                        name, season, episode.get("episode_number")) if season != 1 else "%s ???%s???" % (
                        name, episode.get("episode_number")),
                    "start": episode.get("air_date"),
                    "id": tid,
                    "year": year,
                    "poster": poster_path,
                    "vote_average": episode.get("vote_average") or "???"
                })
            return {"code": 0, "events": episode_events}

    @staticmethod
    def __rss_detail(data):
        rssid = data.get("rssid")
        rsstype = data.get("rsstype")
        if rsstype in ['nm', 'hm', 'dbom', 'dbhm', 'dbnm', 'dbtop', 'MOV', '??????']:
            rss = SqlHelper.get_rss_movies(rssid=rssid)
            if not rss:
                return {"code": 1}
            rss_info = Torrent.get_rss_note_item(rss[0][4])
            rssdetail = {"rssid": rssid,
                         "name": rss[0][0],
                         "year": rss[0][1],
                         "tmdbid": rss[0][2],
                         "r_sites": rss_info.get("rss_sites"),
                         "s_sites": rss_info.get("search_sites"),
                         "over_edition": rss_info.get("over_edition"),
                         "filter": rss_info.get("filter_map"),
                         "type": "MOV"}
        else:
            rss = SqlHelper.get_rss_tvs(rssid=rssid)
            if not rss:
                return {"code": 1}
            rss_info = Torrent.get_rss_note_item(rss[0][5])
            rssdetail = {"rssid": rssid,
                         "name": rss[0][0],
                         "year": rss[0][1],
                         "season": rss[0][2],
                         "tmdbid": rss[0][3],
                         "r_sites": rss_info.get("rss_sites"),
                         "s_sites": rss_info.get("search_sites"),
                         "over_edition": rss_info.get("over_edition"),
                         "filter": rss_info.get("filter_map"),
                         "total_ep": rss_info.get("episode_info", {}).get("total"),
                         "current_ep": rss_info.get("episode_info", {}).get("current"),
                         "type": "TV"}

        return {"code": 0, "detail": rssdetail}

    @staticmethod
    def __modify_tmdb_cache(data):
        """
        ??????TMDB???????????????
        """
        if MetaHelper().modify_meta_data(data.get("key"), data.get("title")):
            MetaHelper().save_meta_data(force=True)
        return {"code": 0}

    @staticmethod
    def __truncate_blacklist(data):
        """
        ?????????????????????????????????
        """
        SqlHelper.truncate_transfer_blacklist()
        return {"code": 0}

    @staticmethod
    def __truncate_rsshistory(data):
        """
        ??????RSS????????????
        """
        SqlHelper.truncate_rss_history()
        SqlHelper.truncate_rss_episodes()
        return {"code": 0}

    @staticmethod
    def __add_brushtask(data):
        """
        ??????????????????
        """
        # ?????????
        brushtask_id = data.get("brushtask_id")
        brushtask_name = data.get("brushtask_name")
        brushtask_site = data.get("brushtask_site")
        brushtask_interval = data.get("brushtask_interval")
        brushtask_downloader = data.get("brushtask_downloader")
        brushtask_totalsize = data.get("brushtask_totalsize")
        brushtask_state = data.get("brushtask_state")
        brushtask_transfer = 'Y' if data.get("brushtask_transfer") else 'N'
        brushtask_sendmessage = 'Y' if data.get("brushtask_sendmessage") else 'N'
        brushtask_forceupload = 'Y' if data.get("brushtask_forceupload") else 'N'
        brushtask_free = data.get("brushtask_free")
        brushtask_hr = data.get("brushtask_hr")
        brushtask_torrent_size = data.get("brushtask_torrent_size")
        brushtask_include = data.get("brushtask_include")
        brushtask_exclude = data.get("brushtask_exclude")
        brushtask_dlcount = data.get("brushtask_dlcount")
        brushtask_peercount = data.get("brushtask_peercount")
        brushtask_seedtime = data.get("brushtask_seedtime")
        brushtask_seedratio = data.get("brushtask_seedratio")
        brushtask_seedsize = data.get("brushtask_seedsize")
        brushtask_dltime = data.get("brushtask_dltime")
        brushtask_avg_upspeed = data.get("brushtask_avg_upspeed")
        brushtask_pubdate = data.get("brushtask_pubdate")
        brushtask_upspeed = data.get("brushtask_upspeed")
        brushtask_downspeed = data.get("brushtask_downspeed")
        # ????????????
        rss_rule = {
            "free": brushtask_free,
            "hr": brushtask_hr,
            "size": brushtask_torrent_size,
            "include": brushtask_include,
            "exclude": brushtask_exclude,
            "dlcount": brushtask_dlcount,
            "peercount": brushtask_peercount,
            "pubdate": brushtask_pubdate,
            "upspeed": brushtask_upspeed,
            "downspeed": brushtask_downspeed
        }
        # ????????????
        remove_rule = {
            "time": brushtask_seedtime,
            "ratio": brushtask_seedratio,
            "uploadsize": brushtask_seedsize,
            "dltime": brushtask_dltime,
            "avg_upspeed": brushtask_avg_upspeed
        }
        # ????????????
        item = {
            "name": brushtask_name,
            "site": brushtask_site,
            "free": brushtask_free,
            "interval": brushtask_interval,
            "downloader": brushtask_downloader,
            "seed_size": brushtask_totalsize,
            "transfer": brushtask_transfer,
            "state": brushtask_state,
            "rss_rule": rss_rule,
            "remove_rule": remove_rule
        }
        SqlHelper.insert_brushtask(brushtask_id, item)

        # ??????????????????
        DictHelper.set(SystemDictType.BrushMessageSwitch.value, brushtask_site, brushtask_sendmessage)
        # ?????????????????????????????????
        DictHelper.set(SystemDictType.BrushForceUpSwitch.value, brushtask_site, brushtask_forceupload)

        # ?????????????????????
        BrushTask().init_config()
        return {"code": 0}

    @staticmethod
    def __del_brushtask(data):
        """
        ??????????????????
        """
        brush_id = data.get("id")
        if brush_id:
            SqlHelper.delete_brushtask(brush_id)
            # ?????????????????????
            BrushTask().init_config()
            return {"code": 0}
        return {"code": 1}

    @staticmethod
    def __brushtask_detail(data):
        """
        ????????????????????????
        """
        brush_id = data.get("id")
        brushtask = SqlHelper.get_brushtasks(brush_id)
        if not brushtask:
            return {"code": 1, "task": {}}
        scheme, netloc = StringUtils.get_url_netloc(brushtask[0][17])
        sendmessage_switch = DictHelper.get(SystemDictType.BrushMessageSwitch.value, brushtask[0][2])
        forceupload_switch = DictHelper.get(SystemDictType.BrushForceUpSwitch.value, brushtask[0][2])
        task = {
            "id": brushtask[0][0],
            "name": brushtask[0][1],
            "site": brushtask[0][2],
            "interval": brushtask[0][4],
            "state": brushtask[0][5],
            "downloader": brushtask[0][6],
            "transfer": brushtask[0][7],
            "free": brushtask[0][8],
            "rss_rule": eval(brushtask[0][9]),
            "remove_rule": eval(brushtask[0][10]),
            "seed_size": brushtask[0][11],
            "download_count": brushtask[0][12],
            "remove_count": brushtask[0][13],
            "download_size": StringUtils.str_filesize(brushtask[0][14]),
            "upload_size": StringUtils.str_filesize(brushtask[0][15]),
            "lst_mod_date": brushtask[0][16],
            "site_url": "%s://%s" % (scheme, netloc),
            "sendmessage": sendmessage_switch,
            "forceupload": forceupload_switch
        }
        return {"code": 0, "task": task}

    @staticmethod
    def __add_downloader(data):
        """
        ????????????????????????
        """
        test = data.get("test")
        dl_id = data.get("id")
        dl_name = data.get("name")
        dl_type = data.get("type")
        user_config = {"host": data.get("host"),
                       "port": data.get("port"),
                       "username": data.get("username"),
                       "password": data.get("password"),
                       "save_dir": data.get("save_dir")}
        if test:
            # ??????
            if dl_type == "qbittorrent":
                downloader = Qbittorrent(user_config=user_config)
            else:
                downloader = Transmission(user_config=user_config)
            if downloader.get_status():
                return {"code": 0}
            else:
                return {"code": 1}
        else:
            # ??????
            SqlHelper.update_user_downloader(did=dl_id, name=dl_name, dtype=dl_type, user_config=user_config, note=None)
            return {"code": 0}

    @staticmethod
    def __delete_downloader(data):
        """
        ????????????????????????
        """
        dl_id = data.get("id")
        if dl_id:
            SqlHelper.delete_user_downloader(dl_id)
        return {"code": 0}

    @staticmethod
    def __get_downloader(data):
        """
        ????????????????????????
        """
        dl_id = data.get("id")
        if dl_id:
            info = SqlHelper.get_user_downloaders(dl_id)
            return {"code": 0, "info": info[0] if info else None}
        else:
            return {"code": 1}

    def __name_test(self, data):
        """
        ??????????????????
        """
        name = data.get("name")
        if not name:
            return {"code": -1}
        media_info = Media().get_media_info(title=name)
        if not media_info:
            return {"code": 0, "data": {"name": "????????????"}}
        return {"code": 0, "data": self.mediainfo_dict(media_info)}

    @staticmethod
    def mediainfo_dict(media_info):
        if not media_info:
            return {}
        tmdb_id = media_info.tmdb_id
        tmdb_link = ""
        tmdb_S_E_link = ""
        if tmdb_id:
            if media_info.type == MediaType.MOVIE:
                tmdb_link = "https://www.themoviedb.org/movie/" + str(tmdb_id)
            else:
                tmdb_link = "https://www.themoviedb.org/tv/" + str(tmdb_id)
                if media_info.get_season_string():
                    tmdb_S_E_link = "%s/season/%s" % (tmdb_link, media_info.get_season_seq())
                    if media_info.get_episode_string():
                        tmdb_S_E_link = "%s/episode/%s" % (tmdb_S_E_link, media_info.get_episode_seq())
        return {
            "type": media_info.type.value if media_info.type else "",
            "name": media_info.get_name(),
            "title": media_info.title,
            "year": media_info.year,
            "season_episode": media_info.get_season_episode_string(),
            "part": media_info.part,
            "tmdbid": tmdb_id,
            "tmdblink": tmdb_link,
            "tmdb_S_E_link": tmdb_S_E_link,
            "category": media_info.category,
            "restype": media_info.resource_type,
            "pix": media_info.resource_pix,
            "team": media_info.resource_team,
            "video_codec": media_info.video_encode,
            "audio_codec": media_info.audio_encode,
            "org_string": media_info.org_string,
            "ignored_words": media_info.ignored_words,
            "replaced_words": media_info.replaced_words,
            "offset_words": media_info.offset_words
        }

    @staticmethod
    def __rule_test(data):
        title = data.get("title")
        subtitle = data.get("subtitle")
        size = data.get("size")
        if not title:
            return {"code": -1}
        meta_info = MetaInfo(title=title, subtitle=subtitle)
        meta_info.size = float(size) * 1024 ** 3 if size else 0
        match_flag, res_order, rule_name = FilterRule().check_rules(meta_info=meta_info)
        return {
            "code": 0,
            "flag": match_flag,
            "text": "??????" if match_flag else "?????????",
            "name": rule_name if rule_name else "?????????????????????",
            "order": 100 - res_order if res_order else 0
        }

    @staticmethod
    def __net_test(data):
        target = data
        if target == "image.tmdb.org":
            target = target + "/t/p/w500/wwemzKWzjKYJFfCeiB57q3r4Bcm.png"
        if target == "qyapi.weixin.qq.com":
            target = target + "/cgi-bin/message/send"
        target = "https://" + target
        start_time = datetime.datetime.now()
        if target.find("themoviedb") != -1 \
                or target.find("telegram") != -1 \
                or target.find("fanart") != -1 \
                or target.find("tmdb") != -1:
            res = RequestUtils(proxies=Config().get_proxies(), timeout=5).get_res(target)
        else:
            res = RequestUtils(timeout=5).get_res(target)
        seconds = int((datetime.datetime.now() - start_time).microseconds / 1000)
        if not res:
            return {"res": False, "time": "%s ??????" % seconds}
        elif res.ok:
            return {"res": True, "time": "%s ??????" % seconds}
        else:
            return {"res": False, "time": "%s ??????" % seconds}

    @staticmethod
    def __get_site_activity(data):
        """
        ??????site??????[???????????????????????????]
        :param data: {"name":site_name}
        :return:
        """
        if not data or "name" not in data:
            return {"code": 1, "msg": "??????????????????"}

        resp = {"code": 0}

        resp.update({"dataset": Sites().get_pt_site_activity_history(data["name"])})
        return resp

    @staticmethod
    def __get_site_history(data):
        """
        ??????site ??????[???????????????]
        :param data: {"days":????????????}
        :return:
        """
        if not data or "days" not in data or not isinstance(data["days"], int):
            return {"code": 1, "msg": "??????????????????"}

        resp = {"code": 0}
        _, _, site, upload, download = Sites().get_pt_site_statistics_history(data["days"] + 1)

        # ?????????dataset????????????
        dataset = [["site", "upload", "download"]]
        dataset.extend([[site, upload, download] for site, upload, download in zip(site, upload, download)])
        resp.update({"dataset": dataset})
        return resp

    @staticmethod
    def __get_site_seeding_info(data):
        """
        ??????site ?????????????????? ??????????????????
        :param data: {"name":site_name}
        :return:
        """
        if not data or "name" not in data:
            return {"code": 1, "msg": "??????????????????"}

        resp = {"code": 0}

        seeding_info = Sites().get_pt_site_seeding_info(data["name"]).get("seeding_info", [])
        # ?????????dataset????????????
        dataset = [["seeders", "size"]]
        dataset.extend(seeding_info)

        resp.update({"dataset": dataset})
        return resp

    @staticmethod
    def __add_filtergroup(data):
        """
        ???????????????
        """
        name = data.get("name")
        default = data.get("default")
        if not name:
            return {"code": -1}
        SqlHelper.add_filter_group(name, default)
        FilterRule().init_config()
        return {"code": 0}

    @staticmethod
    def __restore_filtergroup(data):
        """
        ?????????????????????
        """
        groupids = data.get("groupids")
        init_rulegroups = data.get("init_rulegroups")
        for groupid in groupids:
            try:
                SqlHelper.delete_filtergroup(groupid)
            except Exception as err:
                print(err)
            for init_rulegroup in init_rulegroups:
                if str(init_rulegroup.get("id")) == groupid:
                    for sql in init_rulegroup.get("sql"):
                        SqlHelper.excute(sql)
        FilterRule().init_config()
        return {"code": 0}

    @staticmethod
    def __set_default_filtergroup(data):
        groupid = data.get("id")
        if not groupid:
            return {"code": -1}
        SqlHelper.set_default_filtergroup(groupid)
        FilterRule().init_config()
        return {"code": 0}

    @staticmethod
    def __del_filtergroup(data):
        groupid = data.get("id")
        SqlHelper.delete_filtergroup(groupid)
        FilterRule().init_config()
        return {"code": 0}

    @staticmethod
    def __add_filterrule(data):
        rule_id = data.get("rule_id")
        item = {
            "group": data.get("group_id"),
            "name": data.get("rule_name"),
            "pri": data.get("rule_pri"),
            "include": data.get("rule_include"),
            "exclude": data.get("rule_exclude"),
            "size": data.get("rule_sizelimit"),
            "free": data.get("rule_free")
        }
        SqlHelper.insert_filter_rule(ruleid=rule_id, item=item)
        FilterRule().init_config()
        return {"code": 0}

    @staticmethod
    def __del_filterrule(data):
        ruleid = data.get("id")
        SqlHelper.delete_filterrule(ruleid)
        FilterRule().init_config()
        return {"code": 0}

    @staticmethod
    def __filterrule_detail(data):
        rid = data.get("ruleid")
        groupid = data.get("groupid")
        ruleinfo = FilterRule().get_rules(groupid=groupid, ruleid=rid)
        if ruleinfo:
            ruleinfo['include'] = "\n".join(ruleinfo.get("include"))
            ruleinfo['exclude'] = "\n".join(ruleinfo.get("exclude"))
        return {"code": 0, "info": ruleinfo}

    @staticmethod
    def get_recommend(data):
        RecommendType = data.get("type")
        CurrentPage = data.get("page")
        if not CurrentPage:
            CurrentPage = 1
        else:
            CurrentPage = int(CurrentPage)
        if RecommendType == "hm":
            # TMDB????????????
            res_list = Media().get_tmdb_hot_movies(CurrentPage)
        elif RecommendType == "ht":
            # TMDB???????????????
            res_list = Media().get_tmdb_hot_tvs(CurrentPage)
        elif RecommendType == "nm":
            # TMDB????????????
            res_list = Media().get_tmdb_new_movies(CurrentPage)
        elif RecommendType == "nt":
            # TMDB???????????????
            res_list = Media().get_tmdb_new_tvs(CurrentPage)
        elif RecommendType == "dbom":
            # ??????????????????
            res_list = DouBan().get_douban_online_movie(CurrentPage)
        elif RecommendType == "dbhm":
            # ??????????????????
            res_list = DouBan().get_douban_hot_movie(CurrentPage)
        elif RecommendType == "dbht":
            # ?????????????????????
            res_list = DouBan().get_douban_hot_tv(CurrentPage)
        elif RecommendType == "dbdh":
            # ??????????????????
            res_list = DouBan().get_douban_hot_anime(CurrentPage)
        elif RecommendType == "dbnm":
            # ??????????????????
            res_list = DouBan().get_douban_new_movie(CurrentPage)
        elif RecommendType == "dbtop":
            # ??????TOP250??????
            res_list = DouBan().get_douban_top250_movie(CurrentPage)
        elif RecommendType == "dbzy":
            # ?????????????????????
            res_list = DouBan().get_douban_hot_show(CurrentPage)
        else:
            res_list = []

        Items = []
        for res in res_list:
            rid = res.get('id')
            orgid = rid
            if RecommendType in ['hm', 'nm', 'dbom', 'dbhm', 'dbnm', 'dbtop']:
                title = res.get('title')
                date = res.get('release_date')
                if date:
                    year = date[0:4]
                else:
                    year = ''
                name = MetaInfo(title).get_name()
                if RecommendType not in ['hm', 'nm']:
                    rid = "DB:%s" % rid
                rssid = SqlHelper.get_rss_movie_id(title=name, tmdbid=rid)
                if rssid:
                    # ?????????
                    fav = 1
                elif MediaServer().check_item_exists(title=name, year=year, tmdbid=rid):
                    # ?????????
                    fav = 2
                else:
                    # ?????????????????????
                    fav = 0
            else:
                title = res.get('name')
                date = res.get('first_air_date')
                if date:
                    year = date[0:4]
                else:
                    year = ''
                name = MetaInfo(title).get_name()
                if RecommendType not in ['ht', 'nt']:
                    rid = "DB:%s" % rid
                rssid = SqlHelper.get_rss_tv_id(title=name, tmdbid=rid)
                if rssid:
                    # ?????????
                    fav = 1
                elif MediaServer().check_item_exists(title=name, tmdbid=rid):
                    # ?????????
                    fav = 2
                else:
                    # ?????????????????????
                    fav = 0
            image = res.get('poster_path')
            if RecommendType in ['hm', 'nm', 'ht', 'nt']:
                image = TMDB_IMAGE_ORIGINAL_URL % image if image else ""
            else:
                # ?????????????????????
                image = image.replace("s_ratio_poster", "m_ratio_poster")
            vote = res.get('vote_average')
            overview = res.get('overview')
            item = {'id': rid,
                    'orgid': orgid,
                    'title': title,
                    'fav': fav,
                    'date': date,
                    'vote': vote,
                    'image': image,
                    'overview': overview,
                    'year': year,
                    'rssid': rssid}
            Items.append(item)
        return {"code": 0, "Items": Items}

    @staticmethod
    def get_downloaded(data):
        page = data.get("page")
        Items = SqlHelper.get_download_history(page=page) or []
        return {"code": 0, "Items": Items}

    @staticmethod
    def parse_sites_string(notes):
        if not notes:
            return ""
        rss_info = Torrent.get_rss_note_item(notes)
        rss_site_htmls = ['<span class="badge bg-lime me-1 mb-1" title="????????????">%s</span>' % s for s in
                          rss_info.get("rss_sites") if s]
        search_site_htmls = ['<span class="badge bg-yellow me-1 mb-1" title="????????????">%s</span>' % s for s in
                             rss_info.get("search_sites") if s]

        return "".join(rss_site_htmls) + "".join(search_site_htmls)

    @staticmethod
    def parse_filter_string(notes):
        if not notes:
            return ""
        rss_info = Torrent.get_rss_note_item(notes)
        filter_htmls = []
        if rss_info.get("over_edition"):
            filter_htmls.append('<span class="badge badge-outline text-red me-1 mb-1" title="???????????????">??????</span>')
        if rss_info.get("filter_map") and rss_info.get("filter_map").get("restype"):
            filter_htmls.append(
                '<span class="badge badge-outline text-orange me-1 mb-1">%s</span>' % rss_info.get("filter_map").get(
                    "restype"))
        if rss_info.get("filter_map") and rss_info.get("filter_map").get("pix"):
            filter_htmls.append(
                '<span class="badge badge-outline text-orange me-1 mb-1">%s</span>' % rss_info.get("filter_map").get(
                    "pix"))
        if rss_info.get("filter_map") and rss_info.get("filter_map").get("team"):
            filter_htmls.append(
                '<span class="badge badge-outline text-blue me-1 mb-1">%s</span>' % rss_info.get("filter_map").get(
                    "team"))
        if rss_info.get("filter_map") and rss_info.get("filter_map").get("rule"):
            filter_htmls.append('<span class="badge badge-outline text-orange me-1 mb-1">%s</span>' %
                                FilterRule().get_rule_groups(groupid=rss_info.get("filter_map").get("rule")).get(
                                    "name") or "")
        return "".join(filter_htmls)

    @staticmethod
    def parse_brush_rule_string(rules: dict):
        if not rules:
            return ""
        rule_filter_string = {"gt": ">", "lt": "<", "bw": ""}
        rule_htmls = []
        if rules.get("size"):
            sizes = rules.get("size").split("#")
            if sizes[0]:
                if sizes[1]:
                    sizes[1] = sizes[1].replace(",", "-")
                rule_htmls.append(
                    '<span class="badge badge-outline text-blue me-1 mb-1" title="????????????">????????????: %s %sGB</span>'
                    % (rule_filter_string.get(sizes[0]), sizes[1]))
        if rules.get("pubdate"):
            pubdates = rules.get("pubdate").split("#")
            if pubdates[0]:
                if pubdates[1]:
                    pubdates[1] = pubdates[1].replace(",", "-")
                rule_htmls.append(
                    '<span class="badge badge-outline text-blue me-1 mb-1" title="????????????">????????????: %s %s??????</span>'
                    % (rule_filter_string.get(pubdates[0]), pubdates[1]))
        if rules.get("upspeed"):
            rule_htmls.append('<span class="badge badge-outline text-blue me-1 mb-1" title="????????????">????????????: %sB/s</span>'
                              % StringUtils.str_filesize(int(rules.get("upspeed")) * 1024))
        if rules.get("downspeed"):
            rule_htmls.append('<span class="badge badge-outline text-blue me-1 mb-1" title="????????????">????????????: %sB/s</span>'
                              % StringUtils.str_filesize(int(rules.get("downspeed")) * 1024))
        if rules.get("include"):
            rule_htmls.append('<span class="badge badge-outline text-green me-1 mb-1" title="????????????">??????: %s</span>'
                              % rules.get("include"))
        if rules.get("hr"):
            rule_htmls.append('<span class="badge badge-outline text-red me-1 mb-1" title="??????HR">??????: HR</span>')
        if rules.get("exclude"):
            rule_htmls.append('<span class="badge badge-outline text-red me-1 mb-1" title="????????????">??????: %s</span>'
                              % rules.get("exclude"))
        if rules.get("dlcount"):
            rule_htmls.append('<span class="badge badge-outline text-blue me-1 mb-1" title="????????????????????????">????????????: %s</span>'
                              % rules.get("dlcount"))
        if rules.get("peercount"):
            peer_counts = None
            if rules.get("peercount") == "#":
                peer_counts = None
            elif "#" in rules.get("peercount"):
                peer_counts = rules.get("peercount").split("#")
                peer_counts[1] = peer_counts[1].replace(",", "-") if (len(peer_counts) >= 2 and peer_counts[1]) else \
                    peer_counts[1]
            else:
                try:
                    # ???????????????
                    peer_counts = ["lt", int(rules.get("peercount"))]
                except Exception as err:
                    print(err)
                    pass
            if peer_counts:
                rule_htmls.append(
                    '<span class="badge badge-outline text-blue me-1 mb-1" title="????????????????????????">????????????: %s %s</span>'
                    % (rule_filter_string.get(peer_counts[0]), peer_counts[1]))
        if rules.get("time"):
            times = rules.get("time").split("#")
            if times[0]:
                rule_htmls.append(
                    '<span class="badge badge-outline text-orange me-1 mb-1" title="????????????">????????????: %s %s??????</span>'
                    % (rule_filter_string.get(times[0]), times[1]))
        if rules.get("ratio"):
            ratios = rules.get("ratio").split("#")
            if ratios[0]:
                rule_htmls.append(
                    '<span class="badge badge-outline text-orange me-1 mb-1" title="?????????">?????????: %s %s</span>'
                    % (rule_filter_string.get(ratios[0]), ratios[1]))
        if rules.get("uploadsize"):
            uploadsizes = rules.get("uploadsize").split("#")
            if uploadsizes[0]:
                rule_htmls.append(
                    '<span class="badge badge-outline text-orange me-1 mb-1" title="?????????">?????????: %s %sGB</span>'
                    % (rule_filter_string.get(uploadsizes[0]), uploadsizes[1]))
        if rules.get("dltime"):
            dltimes = rules.get("dltime").split("#")
            if dltimes[0]:
                rule_htmls.append(
                    '<span class="badge badge-outline text-orange me-1 mb-1" title="????????????">????????????: %s %s??????</span>'
                    % (rule_filter_string.get(dltimes[0]), dltimes[1]))
        if rules.get("avg_upspeed"):
            avg_upspeeds = rules.get("avg_upspeed").split("#")
            if avg_upspeeds[0]:
                rule_htmls.append(
                    '<span class="badge badge-outline text-orange me-1 mb-1" title="??????????????????">??????????????????: %s %sKB/S</span>'
                    % (rule_filter_string.get(avg_upspeeds[0]), avg_upspeeds[1]))

        return "<br>".join(rule_htmls)

    @staticmethod
    def str_filesize(size):
        return StringUtils.str_filesize(size, pre=1)

    @staticmethod
    def __clear_tmdb_cache(data):
        """
        ??????TMDB??????
        """
        try:
            MetaHelper().clear_meta_data()
            os.remove(MetaHelper().get_meta_data_path())
        except Exception as e:
            return {"code": 0, "msg": str(e)}
        return {"code": 0}

    @staticmethod
    def __check_site_attr(data):
        """
        ??????????????????
        """
        site_attr = Sites().get_grapsite_conf(data.get("url"))
        site_free = site_2xfree = site_hr = False
        if site_attr.get("FREE"):
            site_free = True
        if site_attr.get("2XFREE"):
            site_2xfree = True
        if site_attr.get("HR"):
            site_hr = True
        return {"code": 0, "site_free": site_free, "site_2xfree": site_2xfree, "site_hr": site_hr}

    @staticmethod
    def __refresh_process(data):
        """
        ???????????????
        """
        detail = ProgressHelper().get_process(data.get("type"))
        if detail:
            return {"code": 0, "value": detail.get("value"), "text": detail.get("text")}
        else:
            return {"code": 1, "value": 0, "text": "????????????..."}

    @staticmethod
    def __restory_backup(data):
        """
        ????????????????????????
        """
        filename = data.get("file_name")
        if filename:
            config_path = Config().get_config_path()
            file_path = os.path.join(config_path, filename)
            try:
                shutil.unpack_archive(file_path, config_path, format='zip')
                return {"code": 0, "msg": ""}
            except Exception as e:
                return {"code": 1, "msg": str(e)}
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)

        return {"code": 1, "msg": "???????????????"}

    @staticmethod
    def __start_mediasync(data):
        """
        ?????????????????????
        """
        ThreadHelper().start_thread(MediaServer().sync_mediaserver, ())
        return {"code": 0}

    @staticmethod
    def __mediasync_state(data):
        """
        ?????????????????????????????????
        """
        status = MediaServer().get_mediasync_status()
        if not status:
            return {"code": 0, "text": "?????????"}
        else:
            return {"code": 0, "text": "?????????%s???????????????%s??????????????????%s" % (status.get("movie_count"),
                                                                 status.get("tv_count"),
                                                                 status.get("time"))}

    @staticmethod
    def __get_tvseason_list(data):
        """
        ?????????????????????
        """
        tmdbid = data.get("tmdbid")
        seasons = [
            {"text": "???%s???" % cn2an.an2cn(season.get("season_number"), mode='low'), "num": season.get("season_number")}
            for season in Media().get_tmdb_seasons_list(tmdbid=tmdbid)]
        return {"code": 0, "seasons": seasons}

    @staticmethod
    def __get_userrss_task(data):
        """
        ???????????????????????????
        """
        taskid = data.get("id")
        return {"code": 0, "detail": RssChecker().get_rsstask_info(taskid=taskid)}

    @staticmethod
    def __delete_userrss_task(data):
        """
        ?????????????????????
        """
        if SqlHelper.delete_userrss_task(data.get("id")):
            RssChecker().init_config()
            return {"code": 0}
        else:
            return {"code": 1}

    @staticmethod
    def __update_userrss_task(data):
        """
        ??????????????????????????????
        """
        params = {
            "id": data.get("id"),
            "name": data.get("name"),
            "address": data.get("address"),
            "parser": data.get("parser"),
            "interval": data.get("interval"),
            "uses": data.get("uses"),
            "include": data.get("include"),
            "exclude": data.get("exclude"),
            "filterrule": data.get("filterrule"),
            "state": data.get("state"),
            "note": data.get("note")
        }
        if SqlHelper.update_userrss_task(params):
            RssChecker().init_config()
            return {"code": 0}
        else:
            return {"code": 1}

    @staticmethod
    def __get_rssparser(data):
        """
        ???????????????????????????
        """
        pid = data.get("id")
        return {"code": 0, "detail": RssChecker().get_userrss_parser(pid=pid)}

    @staticmethod
    def __delete_rssparser(data):
        """
        ?????????????????????
        """
        if SqlHelper.delete_userrss_parser(data.get("id")):
            return {"code": 0}
        else:
            return {"code": 1}

    @staticmethod
    def __update_rssparser(data):
        """
        ??????????????????????????????
        """
        params = {
            "id": data.get("id"),
            "name": data.get("name"),
            "type": data.get("type"),
            "format": data.get("format"),
            "params": data.get("params")
        }
        if SqlHelper.update_userrss_parser(params):
            return {"code": 0}
        else:
            return {"code": 1}

    @staticmethod
    def __run_userrss(data):
        RssChecker().check_task_rss(data.get("id"))
        return {"code": 0}

    @staticmethod
    def __run_brushtask(data):
        BrushTask().check_task_rss(data.get("id"))
        return {"code": 0}

    @staticmethod
    def __list_site_resources(data):
        resources = BuiltinIndexer().list(data.get("id"), data.get("page"), data.get("keyword"))
        if not resources:
            return {"code": 1, "msg": "?????????????????????????????????????????????????????????"}
        else:
            return {"code": 0, "data": resources}

    @staticmethod
    def __list_rss_articles(data):
        articles = RssChecker().get_rss_articles(data.get("id"))
        count = len(articles)
        if articles:
            return {"code": 0, "data": articles, "count": count}
        else:
            return {"code": 1, "msg": "??????????????????"}

    def __rss_article_test(self, data):
        taskid = data.get("taskid")
        title = data.get("title")
        if not taskid:
            return {"code": -1}
        if not title:
            return {"code": -1}
        media_info, match_flag, exist_flag = RssChecker().test_rss_articles(taskid=taskid, title=title)
        if not media_info:
            return {"code": 0, "data": {"name": "????????????"}}
        media_dict = self.mediainfo_dict(media_info)
        media_dict.update({"match_flag": match_flag, "exist_flag": exist_flag})
        return {"code": 0, "data": media_dict}

    @staticmethod
    def __list_rss_history(data):
        downloads = []
        historys = SqlHelper.get_userrss_task_history(data.get("id"))
        count = len(historys)
        for history in historys:
            params = {
                "title": history[2],
                "downloader": history[3],
                "date": history[4]
            }
            downloads.append(params)
        if downloads:
            return {"code": 0, "data": downloads, "count": count}
        else:
            return {"code": 1, "msg": "???????????????"}

    @staticmethod
    def __rss_articles_check(data):
        if not data.get("articles"):
            return {"code": 2}
        res = RssChecker().check_rss_articles(flag=data.get("flag"), articles=data.get("articles"))
        if res:
            return {"code": 0}
        else:
            return {"code": 1}

    @staticmethod
    def __rss_articles_download(data):
        if not data.get("articles"):
            return {"code": 2}
        res = RssChecker().download_rss_articles(taskid=data.get("taskid"), articles=data.get("articles"))
        if res:
            return {"code": 0}
        else:
            return {"code": 1}

    @staticmethod
    def __add_custom_word_group(data):
        try:
            tmdb_id = data.get("tmdb_id")
            tmdb_type = data.get("tmdb_type")
            if tmdb_type == "tv":
                if not SqlHelper.is_custom_word_group_existed(tmdbid=tmdb_id, wtype=2):
                    tmdb_info = Media().get_tmdb_info(mtype=MediaType.TV, tmdbid=tmdb_id)
                    if not tmdb_info:
                        return {"code": 1, "msg": "??????????????????????????????TMDB??????"}
                    SqlHelper.insert_custom_word_groups(title=tmdb_info.get("name"),
                                                        year=tmdb_info.get("first_air_date")[0:4],
                                                        wtype=2,
                                                        tmdbid=tmdb_id,
                                                        season_count=tmdb_info.get("number_of_seasons"))
                    return {"code": 0, "msg": ""}
                else:
                    return {"code": 1, "msg": "???????????????TMDB ID????????????"}
            elif tmdb_type == "movie":
                if not SqlHelper.is_custom_word_group_existed(tmdbid=tmdb_id, wtype=1):
                    tmdb_info = Media().get_tmdb_info(mtype=MediaType.MOVIE, tmdbid=tmdb_id)
                    if not tmdb_info:
                        return {"code": 1, "msg": "??????????????????????????????TMDB??????"}
                    SqlHelper.insert_custom_word_groups(title=tmdb_info.get("title"),
                                                        year=tmdb_info.get("release_date")[0:4],
                                                        wtype=1,
                                                        tmdbid=tmdb_id,
                                                        season_count=0)
                    return {"code": 0, "msg": ""}
                else:
                    return {"code": 1, "msg": "???????????????TMDB ID????????????"}
            else:
                return {"code": 1, "msg": "????????????????????????"}
        except Exception as e:
            print(str(e))
            return {"code": 1, "msg": str(e)}

    @staticmethod
    def __delete_custom_word_group(data):
        try:
            wid = data.get("gid")
            SqlHelper.delete_custom_word_group(wid=wid)
            WordsHelper().init_config()
            return {"code": 0, "msg": ""}
        except Exception as e:
            print(str(e))
            return {"code": 1, "msg": str(e)}

    @staticmethod
    def __add_or_edit_custom_word(data):
        try:
            wid = data.get("id")
            gid = data.get("gid")
            group_type = data.get("group_type")
            replaced = data.get("new_replaced")
            replace = data.get("new_replace")
            front = data.get("new_front")
            back = data.get("new_back")
            offset = data.get("new_offset")
            whelp = data.get("new_help")
            wtype = data.get("type")
            season = data.get("season")
            enabled = data.get("enabled")
            regex = data.get("regex")
            if wid:
                SqlHelper.delete_custom_word(wid=wid)
            # ??????
            if group_type == "1":
                season = -2
            # ??????
            if wtype == "1":
                if not SqlHelper.is_custom_words_existed(replaced=replaced):
                    SqlHelper.insert_custom_word(replaced=replaced,
                                                 replace="",
                                                 front="",
                                                 back="",
                                                 offset=0,
                                                 wtype=wtype,
                                                 gid=gid,
                                                 season=season,
                                                 enabled=enabled,
                                                 regex=regex,
                                                 whelp=whelp if whelp else "")
                    WordsHelper().init_config()
                    return {"code": 0, "msg": ""}
                else:
                    return {"code": 1, "msg": "??????????????????\n??????????????????%s???" % replaced}
            # ??????
            elif wtype == "2":
                if not SqlHelper.is_custom_words_existed(replaced=replaced):
                    SqlHelper.insert_custom_word(replaced=replaced,
                                                 replace=replace,
                                                 front="",
                                                 back="",
                                                 offset=0,
                                                 wtype=wtype,
                                                 gid=gid,
                                                 season=season,
                                                 enabled=enabled,
                                                 regex=regex,
                                                 whelp=whelp if whelp else "")
                    WordsHelper().init_config()
                    return {"code": 0, "msg": ""}
                else:
                    return {"code": 1, "msg": "??????????????????\n??????????????????%s???" % replaced}
            # ?????????
            elif wtype == "4":
                if not SqlHelper.is_custom_words_existed(front=front, back=back):
                    SqlHelper.insert_custom_word(replaced="",
                                                 replace="",
                                                 front=front,
                                                 back=back,
                                                 offset=offset,
                                                 wtype=wtype,
                                                 gid=gid,
                                                 season=season,
                                                 enabled=enabled,
                                                 regex=regex,
                                                 whelp=whelp if whelp else "")
                    WordsHelper().init_config()
                    return {"code": 0, "msg": ""}
                else:
                    return {"code": 1, "msg": "??????????????????\n?????????????????????%s@%s???" % (front, back)}
            # ??????+?????????
            elif wtype == "3":
                if not SqlHelper.is_custom_words_existed(replaced=replaced):
                    SqlHelper.insert_custom_word(replaced=replaced,
                                                 replace=replace,
                                                 front=front,
                                                 back=back,
                                                 offset=offset,
                                                 wtype=wtype,
                                                 gid=gid,
                                                 season=season,
                                                 enabled=enabled,
                                                 regex=regex,
                                                 whelp=whelp if whelp else "")
                    WordsHelper().init_config()
                    return {"code": 0, "msg": ""}
                else:
                    return {"code": 1, "msg": "??????????????????\n??????????????????%s???" % replaced}
            else:
                return {"code": 1, "msg": ""}
        except Exception as e:
            print(str(e))
            return {"code": 1, "msg": str(e)}

    @staticmethod
    def __get_custom_word(data):
        try:
            wid = data.get("id")
            word_info = SqlHelper.get_custom_words(wid=wid)[0]
            word = {"id": word_info[0],
                    "replaced": word_info[1],
                    "replace": word_info[2],
                    "front": word_info[3],
                    "back": word_info[4],
                    "offset": word_info[5],
                    "type": word_info[6],
                    "group_id": word_info[7],
                    "season": word_info[8],
                    "enabled": word_info[9],
                    "regex": word_info[10],
                    "help": word_info[11], }
            return {"code": 0, "data": word}
        except Exception as e:
            print(str(e))
            return {"code": 1, "msg": "?????????????????????"}

    @staticmethod
    def __delete_custom_word(data):
        try:
            wid = data.get("id")
            SqlHelper.delete_custom_word(wid)
            WordsHelper().init_config()
            return {"code": 0, "msg": ""}
        except Exception as e:
            return {"code": 1, "msg": str(e)}

    @staticmethod
    def __check_custom_words(data):
        try:
            flag_dict = {"enable": 1, "disable": 0}
            ids_info = data.get("ids_info")
            enabled = flag_dict.get(data.get("flag"))
            ids = [id_info.split("_")[1] for id_info in ids_info]
            for wid in ids:
                SqlHelper.check_custom_word(wid=wid, enabled=enabled)
            WordsHelper().init_config()
            return {"code": 0, "msg": ""}
        except Exception as e:
            print(str(e))
            return {"code": 1, "msg": "???????????????????????????"}

    @staticmethod
    def __export_custom_words(data):
        try:
            note = data.get("note")
            ids_info = data.get("ids_info").split("@")
            group_ids = []
            word_ids = []
            for id_info in ids_info:
                wid = id_info.split("_")
                group_ids.append(wid[0])
                word_ids.append(wid[1])
            export_dict = {}
            for group_id in group_ids:
                if group_id == "-1":
                    export_dict["-1"] = {"id": -1,
                                         "title": "??????",
                                         "type": 1,
                                         "words": {}, }
                else:
                    group_info = SqlHelper.get_custom_word_groups(gid=group_id)[0]
                    export_dict[str(group_info[0])] = {"id": group_info[0],
                                                       "title": group_info[1],
                                                       "year": group_info[2],
                                                       "type": group_info[3],
                                                       "tmdbid": group_info[4],
                                                       "season_count": group_info[5],
                                                       "words": {}, }
            for word_id in word_ids:
                word_info = SqlHelper.get_custom_words(wid=word_id)[0]
                export_dict[str(word_info[7])]["words"][str(word_info[0])] = {"id": word_info[0],
                                                                              "replaced": word_info[1],
                                                                              "replace": word_info[2],
                                                                              "front": word_info[3],
                                                                              "back": word_info[4],
                                                                              "offset": word_info[5],
                                                                              "type": word_info[6],
                                                                              "season": word_info[8],
                                                                              "regex": word_info[10],
                                                                              "help": word_info[11], }
            export_string = json.dumps(export_dict) + "@@@@@@" + str(note)
            string = base64.b64encode(export_string.encode("utf-8")).decode('utf-8')
            return {"code": 0, "string": string}
        except Exception as e:
            print(str(e))
            return {"code": 1, "msg": str(e)}

    @staticmethod
    def __analyse_import_custom_words_code(data):
        try:
            import_code = data.get('import_code')
            string = base64.b64decode(import_code.encode("utf-8")).decode('utf-8').split("@@@@@@")
            note_string = string[1]
            import_dict = json.loads(string[0])
            groups = []
            for group in import_dict.values():
                wid = group.get('id')
                title = group.get("title")
                year = group.get("year")
                wtype = group.get("type")
                tmdbid = group.get("tmdbid")
                season_count = group.get("season_count") or ""
                words = group.get("words")
                if tmdbid:
                    link = "https://www.themoviedb.org/%s/%s" % ("movie" if int(wtype) == 1 else "tv", tmdbid)
                else:
                    link = ""
                groups.append({"id": wid,
                               "name": "%s???%s???" % (title, year) if year else title,
                               "link": link,
                               "type": wtype,
                               "seasons": season_count,
                               "words": words})
            return {"code": 0, "groups": groups, "note_string": note_string}
        except Exception as e:
            print(str(e))
            return {"code": 1, "msg": str(e)}

    @staticmethod
    def __import_custom_words(data):
        try:
            import_code = data.get('import_code')
            ids_info = data.get('ids_info')
            string = base64.b64decode(import_code.encode("utf-8")).decode('utf-8').split("@@@@@@")
            import_dict = json.loads(string[0])
            import_group_ids = [id_info.split("_")[0] for id_info in ids_info]
            group_id_dict = {}
            for import_group_id in import_group_ids:
                import_group_info = import_dict.get(import_group_id)
                if int(import_group_info.get("id")) == -1:
                    group_id_dict["-1"] = -1
                    continue
                title = import_group_info.get("title")
                year = import_group_info.get("year")
                wtype = import_group_info.get("type")
                tmdbid = import_group_info.get("tmdbid")
                season_count = import_group_info.get("season_count")
                if not SqlHelper.is_custom_word_group_existed(tmdbid=tmdbid, wtype=wtype):
                    SqlHelper.insert_custom_word_groups(title=title,
                                                        year=year,
                                                        wtype=wtype,
                                                        tmdbid=tmdbid,
                                                        season_count=season_count)
                group_info = SqlHelper.get_custom_word_groups(tmdbid=tmdbid, wtype=wtype)
                group_id_dict[import_group_id] = group_info[0][0]
            for id_info in ids_info:
                id_info = id_info.split('_')
                import_group_id = id_info[0]
                import_word_id = id_info[1]
                import_word_info = import_dict.get(import_group_id).get("words").get(import_word_id)
                gid = group_id_dict.get(import_group_id)
                replaced = import_word_info.get("replaced")
                replace = import_word_info.get("replace")
                front = import_word_info.get("front")
                back = import_word_info.get("back")
                offset = import_word_info.get("offset")
                whelp = import_word_info.get("help")
                wtype = int(import_word_info.get("type"))
                season = import_word_info.get("season")
                regex = import_word_info.get("regex")
                # ??????, ??????, ??????+?????????
                if wtype in [1, 2, 3]:
                    if SqlHelper.is_custom_words_existed(replaced=replaced):
                        return {"code": 1, "msg": "??????????????????\n??????????????????%s???" % replaced}
                # ?????????
                elif wtype == 4:
                    if SqlHelper.is_custom_words_existed(front=front, back=back):
                        return {"code": 1, "msg": "??????????????????\n?????????????????????%s@%s???" % (front, back)}
                SqlHelper.insert_custom_word(replaced=replaced,
                                             replace=replace,
                                             front=front,
                                             back=back,
                                             offset=offset,
                                             wtype=wtype,
                                             gid=gid,
                                             season=season,
                                             enabled=1,
                                             regex=regex,
                                             whelp=whelp if whelp else "")
            WordsHelper().init_config()
            return {"code": 0, "msg": ""}
        except Exception as e:
            print(str(e))
            return {"code": 1, "msg": str(e)}

    @staticmethod
    def __get_categories(data):
        if data.get("type") == "??????":
            categories = Category().get_movie_categorys()
        elif data.get("type") == "?????????":
            categories = Category().get_tv_categorys()
        else:
            categories = Category().get_anime_categorys()
        return {"code": 0, "category": list(categories), "id": data.get("id"), "value": data.get("value")}

    @staticmethod
    def __delete_rss_history(data):
        rssid = data.get("rssid")
        SqlHelper.delete_rss_history(rssid=rssid)
        return {"code": 0}

    @staticmethod
    def __re_rss_history(data):
        rssid = data.get("rssid")
        rtype = data.get("type")
        rssinfo = SqlHelper.get_rss_history(rtype=rtype, rid=rssid)
        if rssinfo:
            if rtype == "MOV":
                mtype = MediaType.MOVIE
            else:
                mtype = MediaType.TV
            if rssinfo[0][6]:
                season = int(str(rssinfo[0][6]).replace("S", ""))
            else:
                season = None
            code, msg, _ = Subscribe.add_rss_subscribe(mtype=mtype,
                                                       name=rssinfo[0][3],
                                                       year=rssinfo[0][4],
                                                       season=season,
                                                       tmdbid=rssinfo[0][5],
                                                       total_ep=rssinfo[0][9],
                                                       current_ep=rssinfo[0][10])
            return {"code": code, "msg": msg}
        else:
            return {"code": 1, "msg": "???????????????????????????"}

    @staticmethod
    def __share_filtergroup(data):
        gid = data.get("id")
        group_info = SqlHelper.get_config_filter_group(gid=gid)
        if not group_info:
            return {"code": 1, "msg": "??????????????????"}
        group_rules = SqlHelper.get_config_filter_rule(groupid=gid)
        if not group_rules:
            return {"code": 1, "msg": "???????????????????????????"}
        rules = []
        for rule in group_rules:
            rules.append({
                "name": rule[2],
                "pri": rule[3],
                "include": rule[4],
                "exclude": rule[5],
                "size": rule[6],
                "free": rule[7]
            })
        rule_json = {
            "name": group_info[0][1],
            "rules": rules
        }
        json_string = base64.b64encode(json.dumps(rule_json).encode("utf-8")).decode('utf-8')
        return {"code": 0, "string": json_string}

    @staticmethod
    def __import_filtergroup(data):
        content = data.get("content")
        try:
            json_str = base64.b64decode(str(content).encode("utf-8")).decode('utf-8')
            json_obj = json.loads(json_str)
            if json_obj:
                if not json_obj.get("name"):
                    return {"code": 1, "msg": "?????????????????????"}
                SqlHelper.add_filter_group(name=json_obj.get("name"))
                group_id = SqlHelper.get_filter_groupid_by_name(json_obj.get("name"))
                if not group_id:
                    return {"code": 1, "msg": "?????????????????????"}
                if json_obj.get("rules"):
                    for rule in json_obj.get("rules"):
                        SqlHelper.insert_filter_rule(item={
                            "group": group_id,
                            "name": rule.get("name"),
                            "pri": rule.get("pri"),
                            "include": rule.get("include"),
                            "exclude": rule.get("exclude"),
                            "size": rule.get("size"),
                            "free": rule.get("free")
                        })
                FilterRule().init_config()
            return {"code": 0, "msg": ""}
        except Exception as err:
            return {"code": 1, "msg": "????????????????????????%s" % str(err)}
