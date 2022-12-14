import difflib
import os
import random
import re
import traceback
from functools import lru_cache

import zhconv
from lxml import etree

import log
from app.media import MetaInfo
from app.utils import PathUtils, EpisodeFormat, RequestUtils, NumberUtils, StringUtils
from config import Config, KEYWORD_BLACKLIST, KEYWORD_SEARCH_WEIGHT_3, KEYWORD_SEARCH_WEIGHT_2, KEYWORD_SEARCH_WEIGHT_1, \
    KEYWORD_STR_SIMILARITY_THRESHOLD, KEYWORD_DIFF_SCORE_THRESHOLD, TMDB_IMAGE_ORIGINAL_URL, RMT_MEDIAEXT, \
    DEFAULT_TMDB_PROXY
from app.helper import MetaHelper
from app.media.tmdbv3api import TMDb, Search, Movie, TV, Person, Find
from app.media.tmdbv3api.exceptions import TMDbException
from app.media.doubanv2api import DoubanApi
from app.utils.cache_manager import cacheman
from app.utils.types import MediaType, MatchMode


class Media:
    # TheMovieDB
    tmdb = None
    search = None
    movie = None
    tv = None
    person = None
    find = None
    meta = None
    __rmt_match_mode = None
    __search_keyword = None

    def __init__(self):
        self.init_config()
        self.douban = DoubanApi()

    def init_config(self):
        config = Config()
        app = config.get_config('app')
        laboratory = config.get_config('laboratory')
        if app:
            if app.get('rmt_tmdbkey'):
                self.tmdb = TMDb()
                if laboratory.get('tmdb_proxy'):
                    self.tmdb.domain = DEFAULT_TMDB_PROXY
                else:
                    self.tmdb.domain = app.get("tmdb_domain")
                self.tmdb.cache = True
                self.tmdb.api_key = app.get('rmt_tmdbkey')
                self.tmdb.language = 'zh-CN'
                self.tmdb.proxies = config.get_proxies()
                self.tmdb.debug = True
                self.search = Search()
                self.movie = Movie()
                self.tv = TV()
                self.find = Find()
                self.person = Person()
                self.meta = MetaHelper()
            rmt_match_mode = app.get('rmt_match_mode', 'normal')
            if rmt_match_mode:
                rmt_match_mode = rmt_match_mode.upper()
            else:
                rmt_match_mode = "NORMAL"
            if rmt_match_mode == "STRICT":
                self.__rmt_match_mode = MatchMode.STRICT
            else:
                self.__rmt_match_mode = MatchMode.NORMAL
        laboratory = config.get_config('laboratory')
        if laboratory:
            self.__search_keyword = laboratory.get("search_keyword")

    @staticmethod
    def __compare_tmdb_names(file_name, tmdb_names):
        """
        ????????????????????????????????????????????????????????????
        :param file_name: ?????????????????????????????????
        :param tmdb_names: TMDB???????????????
        :return: True or False
        """
        if not file_name or not tmdb_names:
            return False
        if not isinstance(tmdb_names, list):
            tmdb_names = [tmdb_names]
        file_name = StringUtils.handler_special_chars(file_name).upper()
        for tmdb_name in tmdb_names:
            tmdb_name = StringUtils.handler_special_chars(tmdb_name).strip().upper()
            if file_name == tmdb_name:
                return True
        return False

    def __search_tmdb_allnames(self, mtype: MediaType, tmdb_id):
        """
        ??????tmdb????????????????????????????????????????????????
        :param mtype: ????????????????????????????????????
        :param tmdb_id: TMDB???ID
        :return: ?????????????????????
        """
        if not mtype or not tmdb_id:
            return {}, []
        ret_names = []
        tmdb_info = self.get_tmdb_info(mtype=mtype, tmdbid=tmdb_id)
        if not tmdb_info:
            return {}, []
        if mtype == MediaType.MOVIE:
            alternative_titles = tmdb_info.get("alternative_titles", {}).get("titles", [])
            for alternative_title in alternative_titles:
                title = alternative_title.get("title")
                if title and title not in ret_names:
                    ret_names.append(title)
            translations = tmdb_info.get("translations", {}).get("translations", [])
            for translation in translations:
                title = translation.get("data", {}).get("title")
                if title and title not in ret_names:
                    ret_names.append(title)
        else:
            alternative_titles = tmdb_info.get("alternative_titles", {}).get("results", [])
            for alternative_title in alternative_titles:
                name = alternative_title.get("title")
                if name and name not in ret_names:
                    ret_names.append(name)
            translations = tmdb_info.get("translations", {}).get("translations", [])
            for translation in translations:
                name = translation.get("data", {}).get("name")
                if name and name not in ret_names:
                    ret_names.append(name)
        return tmdb_info, ret_names

    def __search_tmdb(self, file_media_name,
                      search_type,
                      first_media_year=None,
                      media_year=None,
                      season_number=None,
                      language=None):
        """
        ??????tmdb???????????????????????????????????????????????????????????????
        :param file_media_name: ???????????????
        :param search_type: ????????????????????????????????????
        :param first_media_year: ?????????????????????????????????????????????(first_air_date)
        :param media_year: ??????????????????
        :param season_number: ???????????????
        :param language: ??????????????????zh-CN
        :return: TMDB???INFO???????????????search_type?????????media_type???
        """
        if not self.search:
            return None
        if not file_media_name:
            return None
        if language:
            self.tmdb.language = language
        else:
            self.tmdb.language = 'zh-CN'
        # TMDB??????
        info = {}
        if search_type == MediaType.MOVIE:
            year_range = [first_media_year]
            if first_media_year:
                year_range.append(str(int(first_media_year) + 1))
                year_range.append(str(int(first_media_year) - 1))
            for first_media_year in year_range:
                log.debug(
                    f"???Meta???????????????{search_type.value}???{file_media_name}, ??????={StringUtils.xstr(first_media_year)} ...")
                info = self.__search_movie_by_name(file_media_name, first_media_year)
                if info:
                    info['media_type'] = MediaType.MOVIE
                    log.info("???Meta???%s ????????? ?????????TMDBID=%s, ??????=%s, ????????????=%s" % (file_media_name,
                                                                            info.get('id'),
                                                                            info.get('title'),
                                                                            info.get('release_date')))
                    break
        else:
            # ??????????????????????????????????????????????????????
            if media_year and season_number:
                log.debug(f"???Meta???????????????{search_type.value}???{file_media_name}, ??????={season_number}, ????????????={media_year} ...")
                info = self.__search_tv_by_season(file_media_name,
                                                  media_year,
                                                  season_number)
            if not info:
                log.debug(
                    f"???Meta???????????????{search_type.value}???{file_media_name}, ??????={StringUtils.xstr(first_media_year)} ...")
                info = self.__search_tv_by_name(file_media_name,
                                                first_media_year)
            if info:
                info['media_type'] = MediaType.TV
                log.info("???Meta???%s ????????? ????????????TMDBID=%s, ??????=%s, ????????????=%s" % (file_media_name,
                                                                         info.get('id'),
                                                                         info.get('name'),
                                                                         info.get('first_air_date')))
        # ??????
        if info:
            return info
        else:
            log.info("???Meta???%s ????????? %s ???TMDB????????????%s??????!" % (
                file_media_name, StringUtils.xstr(first_media_year), search_type.value if search_type else ""))
            return None

    def __search_movie_by_name(self, file_media_name, first_media_year):
        """
        ????????????????????????TMDB??????
        :param file_media_name: ??????????????????????????????
        :param first_media_year: ??????????????????
        :return: ?????????????????????
        """
        try:
            if first_media_year:
                movies = self.search.movies({"query": file_media_name, "year": first_media_year})
            else:
                movies = self.search.movies({"query": file_media_name})
        except TMDbException as err:
            log.error(f"???Meta?????????TMDB?????????{str(err)}")
            return None
        except Exception as e:
            log.error(f"???Meta?????????TMDB?????????{str(e)}")
            return None
        log.debug(f"???Meta???API?????????{str(self.search.total_results)}")
        if len(movies) == 0:
            log.debug(f"???Meta???{file_media_name} ???????????????????????????!")
            return None
        else:
            info = {}
            if first_media_year:
                for movie in movies:
                    if movie.get('release_date'):
                        if self.__compare_tmdb_names(file_media_name, movie.get('title')) \
                                and movie.get('release_date')[0:4] == str(first_media_year):
                            return movie
                        if self.__compare_tmdb_names(file_media_name, movie.get('original_title')) \
                                and movie.get('release_date')[0:4] == str(first_media_year):
                            return movie
            else:
                for movie in movies:
                    if self.__compare_tmdb_names(file_media_name, movie.get('title')) \
                            or self.__compare_tmdb_names(file_media_name, movie.get('original_title')):
                        return movie
            if not info:
                index = 0
                for movie in movies:
                    if first_media_year:
                        if not movie.get('release_date'):
                            continue
                        if movie.get('release_date')[0:4] != str(first_media_year):
                            continue
                        index += 1
                        info, names = self.__search_tmdb_allnames(MediaType.MOVIE, movie.get("id"))
                        if self.__compare_tmdb_names(file_media_name, names):
                            return info
                    else:
                        index += 1
                        info, names = self.__search_tmdb_allnames(MediaType.MOVIE, movie.get("id"))
                        if self.__compare_tmdb_names(file_media_name, names):
                            return info
                    if index > 5:
                        break
        return {}

    def __search_tv_by_name(self, file_media_name, first_media_year):
        """
        ???????????????????????????TMDB??????
        :param file_media_name: ?????????????????????????????????
        :param first_media_year: ????????????????????????
        :return: ?????????????????????
        """
        try:
            if first_media_year:
                tvs = self.search.tv_shows({"query": file_media_name, "first_air_date_year": first_media_year})
            else:
                tvs = self.search.tv_shows({"query": file_media_name})
        except TMDbException as err:
            log.error(f"???Meta?????????TMDB?????????{str(err)}")
            return None
        except Exception as e:
            log.error(f"???Meta?????????TMDB?????????{str(e)}")
            return None
        log.debug(f"???Meta???API?????????{str(self.search.total_results)}")
        if len(tvs) == 0:
            log.debug(f"???Meta???{file_media_name} ???????????????????????????!")
            return None
        else:
            info = {}
            if first_media_year:
                for tv in tvs:
                    if tv.get('first_air_date'):
                        if self.__compare_tmdb_names(file_media_name, tv.get('name')) \
                                and tv.get('first_air_date')[0:4] == str(first_media_year):
                            return tv
                        if self.__compare_tmdb_names(file_media_name, tv.get('original_name')) \
                                and tv.get('first_air_date')[0:4] == str(first_media_year):
                            return tv
            else:
                for tv in tvs:
                    if self.__compare_tmdb_names(file_media_name, tv.get('name')) \
                            or self.__compare_tmdb_names(file_media_name, tv.get('original_name')):
                        return tv
            if not info:
                index = 0
                for tv in tvs:
                    if first_media_year:
                        if not tv.get('first_air_date'):
                            continue
                        if tv.get('first_air_date')[0:4] != str(first_media_year):
                            continue
                        index += 1
                        info, names = self.__search_tmdb_allnames(MediaType.TV, tv.get("id"))
                        if self.__compare_tmdb_names(file_media_name, names):
                            return info
                    else:
                        index += 1
                        info, names = self.__search_tmdb_allnames(MediaType.TV, tv.get("id"))
                        if self.__compare_tmdb_names(file_media_name, names):
                            return info
                    if index > 5:
                        break
        return {}

    def __search_tv_by_season(self, file_media_name, media_year, season_number):
        """
        ??????????????????????????????????????????????????????TMDB
        :param file_media_name: ?????????????????????????????????
        :param media_year: ????????????
        :param season_number: ?????????
        :return: ?????????????????????
        """

        def __season_match(tv_info, season_year):
            if not tv_info:
                return False
            try:
                seasons = self.get_tmdb_seasons_list(tv_info=tv_info)
                for season in seasons:
                    if season.get("air_date") and season.get("season_number"):
                        if season.get("air_date")[0:4] == str(season_year) \
                                and season.get("season_number") == int(season_number):
                            return True
            except Exception as e1:
                log.error(f"???Meta?????????TMDB?????????{e1}")
                return False
            return False

        try:
            tvs = self.search.tv_shows({"query": file_media_name})
        except TMDbException as err:
            log.error(f"???Meta?????????TMDB?????????{str(err)}")
            return None
        except Exception as e:
            log.error(f"???Meta?????????TMDB?????????{e}")
            return None

        if len(tvs) == 0:
            log.debug("???Meta???%s ????????????%s????????????!" % (file_media_name, season_number))
            return None
        else:
            for tv in tvs:
                if (self.__compare_tmdb_names(file_media_name, tv.get('name'))
                    or self.__compare_tmdb_names(file_media_name, tv.get('original_name'))) \
                        and (tv.get('first_air_date') and tv.get('first_air_date')[0:4] == str(media_year)):
                    return tv

            for tv in tvs[:5]:
                info, names = self.__search_tmdb_allnames(MediaType.TV, tv.get("id"))
                if not self.__compare_tmdb_names(file_media_name, names):
                    continue
                if __season_match(tv_info=info, season_year=media_year):
                    return info
        return {}

    def __search_multi_tmdb(self, file_media_name):
        """
        ?????????????????????????????????????????????????????????
        :param file_media_name: ??????????????????????????????
        :return: ?????????????????????
        """
        try:
            multis = self.search.multi({"query": file_media_name}) or []
        except TMDbException as err:
            log.error(f"???Meta?????????TMDB?????????{str(err)}")
            return None
        except Exception as e:
            log.error(f"???Meta?????????TMDB?????????{str(e)}")
            return None
        log.debug(f"???Meta???API?????????{str(self.search.total_results)}")
        if len(multis) == 0:
            log.debug(f"???Meta???{file_media_name} ????????????????????????!")
            return None
        else:
            info = {}
            for multi in multis:
                if multi.get("media_type") == "movie":
                    if self.__compare_tmdb_names(file_media_name, multi.get('title')) \
                            or self.__compare_tmdb_names(file_media_name, multi.get('original_title')):
                        info = multi
                elif multi.get("media_type") == "tv":
                    if self.__compare_tmdb_names(file_media_name, multi.get('name')) \
                            or self.__compare_tmdb_names(file_media_name, multi.get('original_name')):
                        info = multi
            if not info:
                for multi in multis[:5]:
                    if multi.get("media_type") == "movie":
                        movie_info, names = self.__search_tmdb_allnames(MediaType.MOVIE, multi.get("id"))
                        if self.__compare_tmdb_names(file_media_name, names):
                            info = movie_info
                    elif multi.get("media_type") == "tv":
                        tv_info, names = self.__search_tmdb_allnames(MediaType.TV, multi.get("id"))
                        if self.__compare_tmdb_names(file_media_name, names):
                            info = tv_info
        # ??????
        if info:
            info['media_type'] = MediaType.MOVIE if info.get('media_type') == 'movie' else MediaType.TV
            return info
        else:
            log.info("???Meta???%s ???TMDB????????????????????????!" % file_media_name)
            return None

    @lru_cache(maxsize=128)
    def __search_tmdb_web(self, file_media_name, mtype: MediaType):
        """
        ??????TMDB????????????????????????????????????????????????????????????
        :param file_media_name: ??????
        """
        if not file_media_name:
            return None
        if StringUtils.is_chinese(file_media_name):
            return None
        log.info("???Meta????????????TheDbMovie???????????????%s ..." % file_media_name)
        tmdb_url = "https://www.themoviedb.org/search?query=%s" % file_media_name
        res = RequestUtils(timeout=5).get_res(url=tmdb_url)
        if res and res.status_code == 200:
            html_text = res.text
            if not html_text:
                return None
            try:
                tmdb_links = []
                html = etree.HTML(html_text)
                links = html.xpath("//a[@data-id]/@href")
                for link in links:
                    if not link or (not link.startswith("/tv") and not link.startswith("/movie")):
                        continue
                    if link not in tmdb_links:
                        tmdb_links.append(link)
                if len(tmdb_links) == 1:
                    tmdbinfo = self.get_tmdb_info(
                        mtype=MediaType.TV if tmdb_links[0].startswith("/tv") else MediaType.MOVIE,
                        tmdbid=tmdb_links[0].split("/")[-1])
                    if mtype == MediaType.TV and tmdbinfo.get('media_type') != MediaType.TV:
                        return {}
                    if tmdbinfo.get('media_type') == MediaType.MOVIE:
                        log.info("???Meta???%s ???WEB????????? ?????????TMDBID=%s, ??????=%s, ????????????=%s" % (file_media_name,
                                                                                    tmdbinfo.get('id'),
                                                                                    tmdbinfo.get('title'),
                                                                                    tmdbinfo.get('release_date')))
                    else:
                        log.info("???Meta???%s ???WEB????????? ????????????TMDBID=%s, ??????=%s, ????????????=%s" % (file_media_name,
                                                                                     tmdbinfo.get('id'),
                                                                                     tmdbinfo.get('name'),
                                                                                     tmdbinfo.get('first_air_date')))
                    return tmdbinfo
                elif len(tmdb_links) > 1:
                    log.info("???Meta???%s TMDB???????????????????????????%s" % (file_media_name, len(tmdb_links)))
                else:
                    log.info("???Meta???%s TMDB?????????????????????????????????" % file_media_name)
            except Exception as err:
                log.console(str(err))
        return {}

    def get_tmdb_info(self, mtype: MediaType = None, title=None, year=None, tmdbid=None, language=None):
        """
        ???????????????????????????TMDB??????????????????????????????
        :param mtype: ?????????????????????????????????????????????????????????????????????????????????
        :param title: ??????
        :param year: ??????
        :param tmdbid: TMDB???ID??????tmdbid???????????????tmdbid??????????????????????????????
        :param language: ??????
        """
        if not self.tmdb:
            log.error("???Meta???TMDB API Key ????????????")
            return None
        if language:
            self.tmdb.language = language
        else:
            self.tmdb.language = 'zh-CN'
        if not tmdbid or not mtype:
            if not title:
                return None
            if mtype:
                tmdb_info = self.__search_tmdb(file_media_name=title, first_media_year=year, search_type=mtype)
            else:
                tmdb_info = self.__search_multi_tmdb(file_media_name=title)
        else:
            if mtype == MediaType.MOVIE:
                tmdb_info = self.__get_tmdb_movie_detail(tmdbid)
                if tmdb_info:
                    tmdb_info['media_type'] = MediaType.MOVIE
            else:
                tmdb_info = self.__get_tmdb_tv_detail(tmdbid)
                if tmdb_info:
                    tmdb_info['media_type'] = MediaType.TV
            if tmdb_info:
                tmdb_info['genre_ids'] = self.__get_genre_ids_from_detail(tmdb_info.get('genres'))
        if tmdb_info:
            # ???????????????
            org_title = tmdb_info.get("title") if tmdb_info.get("media_type") == MediaType.MOVIE else tmdb_info.get(
                "name")
            if not StringUtils.is_chinese(org_title) and self.tmdb.language == 'zh-CN':
                if tmdb_info.get("alternative_titles"):
                    cn_title = self.__get_tmdb_chinese_title(tmdbinfo=tmdb_info)
                else:
                    cn_title = self.__get_tmdb_chinese_title(tmdbid=tmdb_info.get("id"),
                                                             mtype=tmdb_info.get("media_type"))
                if cn_title and cn_title != org_title:
                    if tmdb_info.get("media_type") == MediaType.MOVIE:
                        tmdb_info['title'] = cn_title
                    else:
                        tmdb_info['name'] = cn_title
        return tmdb_info

    def get_tmdb_infos(self, title, year=None, mtype: MediaType = None, num=6):
        """
        ???????????????????????????????????????TMDB???????????????
        """
        if not self.tmdb:
            log.error("???Meta???TMDB API Key ????????????")
            return []
        if not title:
            return []
        if not mtype and not year:
            results = self.__search_multi_tmdbinfos(title)
        else:
            if not mtype:
                results = list(
                    set(self.__search_movie_tmdbinfos(title, year)).union(set(self.__search_tv_tmdbinfos(title, year))))
                # ?????????????????????????????????
                results = sorted(results,
                                 key=lambda x: x.get("release_date") or x.get("first_air_date") or "0000-00-00",
                                 reverse=True)
            elif mtype == MediaType.MOVIE:
                results = self.__search_movie_tmdbinfos(title, year)
            else:
                results = self.__search_tv_tmdbinfos(title, year)
        return results[:num]

    def __search_multi_tmdbinfos(self, title):
        """
        ?????????????????????????????????????????????TMDB??????
        """
        if not title:
            return []
        ret_infos = []
        multis = self.search.multi({"query": title}) or []
        for multi in multis:
            if multi.get("media_type") in ["movie", "tv"]:
                multi['media_type'] = MediaType.MOVIE if multi.get("media_type") == "movie" else MediaType.TV
                ret_infos.append(multi)
        return ret_infos

    def __search_movie_tmdbinfos(self, title, year):
        """
        ?????????????????????????????????TMDB??????
        """
        if not title:
            return []
        ret_infos = []
        if year:
            movies = self.search.movies({"query": title, "year": year}) or []
        else:
            movies = self.search.movies({"query": title}) or []
        for movie in movies:
            if title in movie.get("title"):
                movie['media_type'] = MediaType.MOVIE
                ret_infos.append(movie)
        return ret_infos

    def __search_tv_tmdbinfos(self, title, year):
        """
        ????????????????????????????????????TMDB??????
        """
        if not title:
            return []
        ret_infos = []
        if year:
            tvs = self.search.tv_shows({"query": title, "first_air_date_year": year}) or []
        else:
            tvs = self.search.tv_shows({"query": title}) or []
        for tv in tvs:
            if title in tv.get("name"):
                tv['media_type'] = MediaType.TV
                ret_infos.append(tv)
        return ret_infos

    def get_media_info(self, title, subtitle=None, mtype=None, strict=None, cache=True, chinese=True):
        """
        ????????????????????????????????????????????????????????????TMDB?????????????????????????????????
        :param title: ????????????
        :param subtitle: ???????????????
        :param mtype: ????????????????????????????????????
        :param strict: ????????????????????????true???????????????????????????????????????
        :param cache: ???????????????????????????TRUE
        :param chinese: ?????????????????????????????????????????????????????????
        :return: ??????TMDB?????????MetaInfo??????
        """
        if not self.tmdb:
            log.error("???Meta???TMDB API Key ????????????")
            return None
        if not title:
            return None
        # ??????
        meta_info = MetaInfo(title, subtitle=subtitle)
        if not meta_info.get_name() or not meta_info.type:
            log.warn("???RMT???%s ???????????????????????????" % meta_info.org_string)
            return None
        if mtype:
            meta_info.type = mtype
        media_key = "[%s]%s-%s-%s" % (
            meta_info.type.value, meta_info.get_name(), meta_info.year, meta_info.begin_season)
        if not cache or not self.meta.get_meta_data_by_key(media_key):
            # ???????????????????????????
            if meta_info.type != MediaType.TV and not meta_info.year:
                file_media_info = self.__search_multi_tmdb(file_media_name=meta_info.get_name())
            else:
                if meta_info.type == MediaType.TV:
                    # ???????????????
                    file_media_info = self.__search_tmdb(file_media_name=meta_info.get_name(),
                                                         first_media_year=meta_info.year,
                                                         search_type=meta_info.type,
                                                         media_year=meta_info.year,
                                                         season_number=meta_info.begin_season
                                                         )
                    if not file_media_info and meta_info.year and self.__rmt_match_mode == MatchMode.NORMAL and not strict:
                        # ??????????????????????????????????????????
                        file_media_info = self.__search_tmdb(file_media_name=meta_info.get_name(),
                                                             search_type=meta_info.type
                                                             )
                else:
                    # ????????????????????????
                    file_media_info = self.__search_tmdb(file_media_name=meta_info.get_name(),
                                                         first_media_year=meta_info.year,
                                                         search_type=MediaType.MOVIE
                                                         )
                    # ????????????????????????
                    if not file_media_info:
                        file_media_info = self.__search_tmdb(file_media_name=meta_info.get_name(),
                                                             first_media_year=meta_info.year,
                                                             search_type=MediaType.TV
                                                             )
                    if not file_media_info and self.__rmt_match_mode == MatchMode.NORMAL and not strict:
                        # ???????????????????????????????????????????????????
                        file_media_info = self.__search_multi_tmdb(file_media_name=meta_info.get_name())
            if not file_media_info:
                file_media_info = self.__search_tmdb_web(file_media_name=meta_info.get_name(),
                                                         mtype=meta_info.type)
            if not file_media_info and self.__search_keyword:
                cache_name = cacheman["tmdb_supply"].get(meta_info.get_name())
                is_movie = False
                if not cache_name:
                    cache_name, is_movie = self.__search_engine(meta_info.get_name())
                    cacheman["tmdb_supply"].set(meta_info.get_name(), cache_name)
                if cache_name:
                    log.info("???Meta????????????????????????%s ..." % cache_name)
                    if is_movie:
                        file_media_info = self.__search_tmdb(file_media_name=cache_name, search_type=MediaType.MOVIE)
                    else:
                        file_media_info = self.__search_multi_tmdb(file_media_name=cache_name)
            if file_media_info:
                # ????????????
                self.meta.update_meta_data({media_key: file_media_info})
            else:
                # ???????????????????????????????????????
                self.meta.update_meta_data({media_key: {'id': 0}})
        # ???????????????
        cache_title = self.meta.get_cache_title(key=media_key)
        if cache_title and chinese and not StringUtils.is_chinese(cache_title) and self.tmdb.language == 'zh-CN':
            cache_media_info = self.meta.get_meta_data_by_key(media_key)
            cn_title = self.__get_tmdb_chinese_title(mtype=cache_media_info.get("media_type"),
                                                     tmdbid=cache_media_info.get("id"))
            if cn_title and cn_title != cache_title:
                self.meta.set_cache_title(key=media_key, cn_title=cn_title)
        # ????????????
        meta_info.set_tmdb_info(self.meta.get_meta_data_by_key(media_key))
        return meta_info

    def get_media_info_on_files(self,
                                file_list,
                                tmdb_info=None,
                                media_type=None,
                                season=None,
                                episode_format: EpisodeFormat = None,
                                chinese=True):
        """
        ???????????????????????????TMDB????????????????????????????????????
        :param file_list: ?????????????????????????????????????????????????????????????????????????????????
        :param tmdb_info: ????????????TMDB???????????????TMDB?????????????????????????????????????????????TMDB????????????????????????????????????
        :param media_type: ????????????????????????????????????????????????????????????????????????????????????????????????????????????TMDB???????????????
        :param season: ??????????????????????????????????????????????????????????????????????????????
        :param episode_format: EpisodeFormat
        :param chinese: ?????????????????????????????????????????????????????????
        :return: ??????TMDB??????????????????????????????MetaInfo????????????
        """
        # ??????????????????????????????????????????
        if not self.tmdb:
            log.error("???Meta???TMDB API Key ????????????")
            return {}
        return_media_infos = {}
        # ??????list?????????list
        if not isinstance(file_list, list):
            file_list = [file_list]
        # ????????????????????????????????????????????????????????????????????????????????????????????????
        for file_path in file_list:
            try:
                if not os.path.exists(file_path):
                    log.warn("???Meta???%s ?????????" % file_path)
                    continue
                # ??????????????????
                # ?????????????????????
                file_name = os.path.basename(file_path)
                parent_name = os.path.basename(os.path.dirname(file_path))
                parent_parent_name = os.path.basename(PathUtils.get_parent_paths(file_path, 2))
                # ????????????TMDB??????
                if not tmdb_info:
                    # ??????
                    meta_info = MetaInfo(title=file_name)
                    # ????????????????????????????????????
                    if not meta_info.get_name() or not meta_info.year:
                        parent_info = MetaInfo(parent_name)
                        if not parent_info.get_name() or not parent_info.year:
                            parent_parent_info = MetaInfo(parent_parent_name)
                            parent_info.type = parent_parent_info.type if parent_parent_info.type and parent_info.type != MediaType.TV else parent_info.type
                            parent_info.cn_name = parent_parent_info.cn_name if parent_parent_info.cn_name else parent_info.cn_name
                            parent_info.en_name = parent_parent_info.en_name if parent_parent_info.en_name else parent_info.en_name
                            parent_info.year = parent_parent_info.year if parent_parent_info.year else parent_info.year
                            parent_info.begin_season = NumberUtils.max_ele(parent_info.begin_season,
                                                                           parent_parent_info.begin_season)
                            parent_info.end_season = NumberUtils.max_ele(parent_info.end_season,
                                                                         parent_parent_info.end_season)
                        if not meta_info.get_name():
                            meta_info.cn_name = parent_info.cn_name
                            meta_info.en_name = parent_info.en_name
                        if not meta_info.year:
                            meta_info.year = parent_info.year
                        if parent_info.type and parent_info.type == MediaType.TV \
                                and meta_info.type != MediaType.TV:
                            meta_info.type = parent_info.type
                        if meta_info.type == MediaType.TV:
                            meta_info.begin_season = NumberUtils.max_ele(parent_info.begin_season,
                                                                         meta_info.begin_season)
                            meta_info.end_season = NumberUtils.max_ele(parent_info.end_season, meta_info.end_season)
                    if not meta_info.get_name() or not meta_info.type:
                        log.warn("???RMT???%s ???????????????????????????" % meta_info.org_string)
                        continue
                    media_key = "[%s]%s-%s-%s" % (
                        meta_info.type.value, meta_info.get_name(), meta_info.year, meta_info.begin_season)
                    if not self.meta.get_meta_data_by_key(media_key):
                        # ??????TMDB API
                        file_media_info = self.__search_tmdb(file_media_name=meta_info.get_name(),
                                                             first_media_year=meta_info.year,
                                                             search_type=meta_info.type,
                                                             media_year=meta_info.year,
                                                             season_number=meta_info.begin_season)
                        if not file_media_info:
                            if self.__rmt_match_mode == MatchMode.NORMAL:
                                # ???????????????????????????????????????????????????
                                file_media_info = self.__search_tmdb(file_media_name=meta_info.get_name(),
                                                                     search_type=meta_info.type)
                        if not file_media_info:
                            # ???????????????
                            file_media_info = self.__search_tmdb_web(file_media_name=meta_info.get_name(),
                                                                     mtype=meta_info.type)
                        if not file_media_info and self.__search_keyword:
                            cache_name = cacheman["tmdb_supply"].get(meta_info.get_name())
                            is_movie = False
                            if not cache_name:
                                cache_name, is_movie = self.__search_engine(meta_info.get_name())
                                cacheman["tmdb_supply"].set(meta_info.get_name(), cache_name)
                            if cache_name:
                                log.info("???Meta????????????????????????%s ..." % cache_name)
                                if is_movie:
                                    file_media_info = self.__search_tmdb(file_media_name=cache_name,
                                                                         search_type=MediaType.MOVIE)
                                else:
                                    file_media_info = self.__search_multi_tmdb(file_media_name=cache_name)
                        if file_media_info:
                            # ????????????
                            self.meta.update_meta_data({media_key: file_media_info})
                        else:
                            # ????????????????????????????????????
                            self.meta.update_meta_data({media_key: {'id': 0}})
                    # ???????????????
                    cache_title = self.meta.get_cache_title(key=media_key)
                    if cache_title and chinese and not StringUtils.is_chinese(
                            cache_title) and self.tmdb.language == 'zh-CN':
                        cache_media_info = self.meta.get_meta_data_by_key(media_key)
                        cn_title = self.__get_tmdb_chinese_title(mtype=cache_media_info.get("media_type"),
                                                                 tmdbid=cache_media_info.get("id"))
                        if cn_title and cn_title != cache_title:
                            self.meta.set_cache_title(key=media_key, cn_title=cn_title)
                    # ????????????????????????
                    meta_info.set_tmdb_info(self.meta.get_meta_data_by_key(media_key))
                # ??????TMDB??????
                else:
                    meta_info = MetaInfo(title=file_name, mtype=media_type)
                    meta_info.set_tmdb_info(tmdb_info)
                    if season and meta_info.type != MediaType.MOVIE:
                        meta_info.begin_season = int(season)
                    if episode_format:
                        begin_ep, end_ep = episode_format.split_episode(file_name)
                        if begin_ep is not None:
                            meta_info.begin_episode = begin_ep
                        if end_ep is not None:
                            meta_info.end_episode = end_ep
                return_media_infos[file_path] = meta_info
            except Exception as err:
                log.error("???RMT??????????????????%s - %s" % (str(err), traceback.format_exc()))
        # ????????????
        return return_media_infos

    def get_tmdb_hot_movies(self, page):
        """
        ??????????????????
        :param page: ?????????
        :return: TMDB????????????
        """
        if not self.movie:
            return []
        return self.movie.popular(page)

    def get_tmdb_hot_tvs(self, page):
        """
        ?????????????????????
        :param page: ?????????
        :return: TMDB????????????
        """
        if not self.tv:
            return []
        return self.tv.popular(page)

    def get_tmdb_new_movies(self, page):
        """
        ??????????????????
        :param page: ?????????
        :return: TMDB????????????
        """
        if not self.movie:
            return []
        return self.movie.now_playing(page)

    def get_tmdb_new_tvs(self, page):
        """
        ?????????????????????
        :param page: ?????????
        :return: TMDB????????????
        """
        if not self.tv:
            return []
        return self.tv.on_the_air(page)

    def get_tmdb_upcoming_movies(self, page):
        """
        ????????????????????????
        :param page: ?????????
        :return: TMDB????????????
        """
        if not self.movie:
            return []
        return self.movie.upcoming(page)

    def __get_tmdb_movie_detail(self, tmdbid):
        """
        ?????????????????????
        :param tmdbid: TMDB ID
        :return: TMDB??????
        """
        if not self.movie:
            return {}
        try:
            log.info("???Meta???????????????TMDB?????????%s ..." % tmdbid)
            tmdbinfo = self.movie.details(tmdbid)
            return tmdbinfo
        except Exception as e:
            log.console(str(e))
            return {}

    def __get_tmdb_tv_detail(self, tmdbid):
        """
        ????????????????????????
        :param tmdbid: TMDB ID
        :return: TMDB??????
        """
        if not self.tv:
            return {}
        try:
            log.info("???Meta???????????????TMDB????????????%s ..." % tmdbid)
            tmdbinfo = self.tv.details(tmdbid)
            return tmdbinfo
        except Exception as e:
            log.console(str(e))
            return {}

    def get_tmdb_tv_season_detail(self, tmdbid, season):
        """
        ???????????????????????????
        :param tmdbid: TMDB ID
        :param season: ????????????
        :return: TMDB??????
        """
        if not self.tv:
            return {}
        try:
            log.info("???Meta???????????????TMDB????????????%s?????????%s ..." % (tmdbid, season))
            tmdbinfo = self.tv.season_details(tmdbid, season)
            return tmdbinfo
        except Exception as e:
            log.console(str(e))
            return {}

    def get_tmdb_seasons_list(self, tv_info=None, tmdbid=None):
        """
        ???TMDB?????????????????????????????????
        :param tv_info: TMDB ????????????
        :param tmdbid: TMDB ID ??????tv_info??????tmdbid???????????????TMDB??????????????????
        :return: ??????season_number???episode_count ?????????????????????????????????
        """
        if not tv_info and not tmdbid:
            return []
        if not tv_info and tmdbid:
            tv_info = self.__get_tmdb_tv_detail(tmdbid)
        if not tv_info:
            return []
        seasons = tv_info.get("seasons")
        if not seasons:
            return []
        total_seasons = []
        for season in seasons:
            if season.get("season_number") != 0 and season.get("episode_count") != 0:
                total_seasons.append(
                    {"season_number": season.get("season_number"),
                     "episode_count": season.get("episode_count"),
                     "air_date": season.get("air_date")})
        return total_seasons

    def get_tmdb_season_episodes_num(self, sea: int, tv_info=None, tmdbid=None):
        """
        ???TMDB??????????????????????????????????????????
        :param sea: ???????????????
        :param tv_info: ????????????TMDB????????????
        :param tmdbid: TMDB ID?????????tv_info??????tmdbid???????????????TMDB??????????????????
        :return: ??????????????????
        """
        if not tv_info and not tmdbid:
            return 0
        if not tv_info and tmdbid:
            tv_info = self.__get_tmdb_tv_detail(tmdbid)
        if not tv_info:
            return 0
        seasons = tv_info.get("seasons")
        if not seasons:
            return 0
        for season in seasons:
            if season.get("season_number") == sea:
                return int(season.get("episode_count"))
        return 0

    def get_movie_discover(self, page=1):
        """
        ????????????
        """
        if not self.movie:
            return {}
        try:
            movies = self.movie.discover(page)
            return movies
        except Exception as e:
            log.console(str(e))
            return {}

    @staticmethod
    def __search_engine(feature_name):
        """
        ?????????????????????
        """
        is_movie = False
        if not feature_name:
            return None, is_movie
        # ?????????????????????
        feature_name = re.compile(r"^\w+??????[??????]?", re.IGNORECASE).sub("", feature_name)
        backlist = sorted(KEYWORD_BLACKLIST, key=lambda x: len(x), reverse=True)
        for single in backlist:
            feature_name = feature_name.replace(single, " ")
        if not feature_name:
            return None, is_movie

        def cal_score(strongs, r_dict):
            for i, s in enumerate(strongs):
                if len(strongs) < 5:
                    if i < 2:
                        score = KEYWORD_SEARCH_WEIGHT_3[0]
                    else:
                        score = KEYWORD_SEARCH_WEIGHT_3[1]
                elif len(strongs) < 10:
                    if i < 2:
                        score = KEYWORD_SEARCH_WEIGHT_2[0]
                    else:
                        score = KEYWORD_SEARCH_WEIGHT_2[1] if i < (len(strongs) >> 1) else KEYWORD_SEARCH_WEIGHT_2[2]
                else:
                    if i < 2:
                        score = KEYWORD_SEARCH_WEIGHT_1[0]
                    else:
                        score = KEYWORD_SEARCH_WEIGHT_1[1] if i < (len(strongs) >> 2) else KEYWORD_SEARCH_WEIGHT_1[
                            2] if i < (
                                len(strongs) >> 1) \
                            else KEYWORD_SEARCH_WEIGHT_1[3] if i < (len(strongs) >> 2 + len(strongs) >> 1) else \
                            KEYWORD_SEARCH_WEIGHT_1[
                                4]
                if r_dict.__contains__(s.lower()):
                    r_dict[s.lower()] += score
                    continue
                r_dict[s.lower()] = score

        bing_url = "https://www.cn.bing.com/search?q=%s&qs=n&form=QBRE&sp=-1" % feature_name
        baidu_url = "https://www.baidu.com/s?ie=utf-8&tn=baiduhome_pg&wd=%s" % feature_name
        res_bing = RequestUtils(timeout=5).get_res(url=bing_url)
        res_baidu = RequestUtils(timeout=5).get_res(url=baidu_url)
        ret_dict = {}
        if res_bing and res_bing.status_code == 200:
            html_text = res_bing.text
            if html_text:
                html = etree.HTML(html_text)
                strongs_bing = list(
                    filter(lambda x: (0 if not x else difflib.SequenceMatcher(None, feature_name,
                                                                              x).ratio()) > KEYWORD_STR_SIMILARITY_THRESHOLD,
                           map(lambda x: x.text, html.cssselect(
                               "#sp_requery strong, #sp_recourse strong, #tile_link_cn strong, .b_ad .ad_esltitle~div strong, h2 strong, .b_caption p strong, .b_snippetBigText strong, .recommendationsTableTitle+.b_slideexp strong, .recommendationsTableTitle+table strong, .recommendationsTableTitle+ul strong, .pageRecoContainer .b_module_expansion_control strong, .pageRecoContainer .b_title>strong, .b_rs strong, .b_rrsr strong, #dict_ans strong, .b_listnav>.b_ans_stamp>strong, #b_content #ans_nws .na_cnt strong, .adltwrnmsg strong"))))
                if strongs_bing:
                    title = html.xpath("//aside//h2[@class = \" b_entityTitle\"]/text()")
                    if len(title) > 0:
                        if title:
                            t = re.compile(r"\s*\(\d{4}\)$").sub("", title[0])
                            ret_dict[t] = 200
                            if html.xpath("//aside//div[@data-feedbk-ids = \"Movie\"]"):
                                is_movie = True
                    cal_score(strongs_bing, ret_dict)
        if res_baidu and res_baidu.status_code == 200:
            html_text = res_baidu.text
            if html_text:
                html = etree.HTML(html_text)
                ems = list(
                    filter(lambda x: (0 if not x else difflib.SequenceMatcher(None, feature_name,
                                                                              x).ratio()) > KEYWORD_STR_SIMILARITY_THRESHOLD,
                           map(lambda x: x.text, html.cssselect("em"))))
                if len(ems) > 0:
                    cal_score(ems, ret_dict)
        if not ret_dict:
            return None, False
        ret = sorted(ret_dict.items(), key=lambda d: d[1], reverse=True)
        log.info("???Meta????????????????????????%s ..." % ([k[0] for i, k in enumerate(ret) if i < 4]))
        if len(ret) == 1:
            keyword = ret[0][0]
        else:
            pre = ret[0]
            nextw = ret[1]
            if nextw[0].find(pre[0]) > -1:
                # ??????????????????
                if int(pre[1]) >= 100:
                    keyword = pre[0]
                # ????????????30 ????????? ?????????
                elif int(pre[1]) - int(nextw[1]) > KEYWORD_DIFF_SCORE_THRESHOLD:
                    keyword = pre[0]
                # ???????????????
                elif nextw[0].replace(pre[0], "").strip() == pre[0]:
                    keyword = pre[0]
                # ???????????????
                elif pre[0].isdigit():
                    keyword = nextw[0]
                else:
                    keyword = nextw[0]

            else:
                keyword = pre[0]
        log.info("???Meta????????????????????????%s " % keyword)
        return keyword, is_movie

    @staticmethod
    def __get_genre_ids_from_detail(genres):
        """
        ???TMDB???????????????genre_id??????
        """
        if not genres:
            return []
        genre_ids = []
        for genre in genres:
            genre_ids.append(genre.get('id'))
        return genre_ids

    def __get_tmdb_chinese_title(self, tmdbinfo=None, mtype: MediaType = None, tmdbid=None):
        """
        ??????????????????????????????
        """
        if not tmdbinfo and not tmdbid:
            return None
        if tmdbinfo:
            if tmdbinfo.get("media_type") == MediaType.MOVIE:
                alternative_titles = tmdbinfo.get("alternative_titles", {}).get("titles", [])
            else:
                alternative_titles = tmdbinfo.get("alternative_titles", {}).get("results", [])
        else:
            try:
                if mtype == MediaType.MOVIE:
                    titles_info = self.movie.alternative_titles(tmdbid) or {}
                    alternative_titles = titles_info.get("titles", [])
                else:
                    titles_info = self.tv.alternative_titles(tmdbid) or {}
                    alternative_titles = titles_info.get("results", [])
            except Exception as err:
                log.console(str(err))
                return None
        for alternative_title in alternative_titles:
            iso_3166_1 = alternative_title.get("iso_3166_1")
            if iso_3166_1 == "CN":
                title = alternative_title.get("title")
                if title and StringUtils.is_chinese(title) and zhconv.convert(title, "zh-hans") == title:
                    return title
        if tmdbinfo:
            return tmdbinfo.get("title") if tmdbinfo.get("media_type") == MediaType.MOVIE else tmdbinfo.get("name")
        return None

    def get_tmdbperson_chinese_name(self, person_id):
        """
        ??????TMDB??????????????????
        """
        if not self.person:
            return ""
        alter_names = []
        name = ""
        try:
            aka_names = self.person.details(person_id).get("also_known_as", []) or []
        except Exception as err:
            log.console(str(err))
            return ""
        for aka_name in aka_names:
            if StringUtils.is_chinese(aka_name):
                alter_names.append(aka_name)
        if len(alter_names) == 1:
            name = alter_names[0]
        elif len(alter_names) > 1:
            for alter_name in alter_names:
                if alter_name == zhconv.convert(alter_name, 'zh-hans'):
                    name = alter_name
        return name

    def get_tmdbperson_aka_names(self, person_id):
        """
        ??????????????????
        """
        if not self.person:
            return []
        try:
            aka_names = self.person.details(person_id).get("also_known_as", []) or []
            return aka_names
        except Exception as err:
            log.console(str(err))
            return []

    def __search_douban_id(self, metainfo):
        """
        ????????????????????????????????????????????????????????????ID
        :param metainfo: ?????????????????????????????????
        """
        if metainfo.year:
            year_range = [int(metainfo.year), int(metainfo.year) + 1, int(metainfo.year) - 1]
        else:
            year_range = []
        if metainfo.type == MediaType.MOVIE:
            search_res = self.douban.movie_search(metainfo.title).get("items") or []
            if not search_res:
                return None
            for res in search_res:
                douban_meta = MetaInfo(title=res.get("target", {}).get("title"))
                if metainfo.title == douban_meta.get_name() \
                        and (int(res.get("target", {}).get("year")) in year_range or not year_range):
                    return res.get("target_id")
            return None
        elif metainfo.type == MediaType.TV:
            search_res = self.douban.tv_search(metainfo.title).get("items") or []
            if not search_res:
                return None
            for res in search_res:
                douban_meta = MetaInfo(title=res.get("target", {}).get("title"))
                if metainfo.title == douban_meta.get_name() \
                        and (str(res.get("target", {}).get("year")) == str(metainfo.year) or not metainfo.year):
                    return res.get("target_id")
                if metainfo.title == douban_meta.get_name() \
                        and metainfo.get_season_string() == douban_meta.get_season_string():
                    return res.get("target_id")
            return search_res[0].get("target_id")

    def get_douban_info(self, metainfo):
        """
        ???????????????????????????????????????
        :param metainfo: ?????????????????????????????????
        """
        doubanid = self.__search_douban_id(metainfo)
        if not doubanid:
            return None
        if metainfo.type == MediaType.MOVIE:
            douban_info = self.douban.movie_detail(doubanid)
            celebrities = self.douban.movie_celebrities(doubanid)
            if douban_info and celebrities:
                douban_info["directors"] = celebrities.get("directors")
                douban_info["actors"] = celebrities.get("actors")
            return douban_info
        elif metainfo.type == MediaType.TV:
            douban_info = self.douban.tv_detail(doubanid)
            celebrities = self.douban.tv_celebrities(doubanid)
            if douban_info and celebrities:
                douban_info["directors"] = celebrities.get("directors")
                douban_info["actors"] = celebrities.get("actors")
            return douban_info

    def get_random_discover_backdrop(self):
        """
        ??????TMDB?????????????????????????????????
        """
        movies = self.get_movie_discover()
        if movies:
            backdrops = [movie.get("backdrop_path") for movie in movies.get("results")]
            return TMDB_IMAGE_ORIGINAL_URL % backdrops[round(random.uniform(0, len(backdrops) - 1))]
        return ""

    def save_rename_cache(self, path, tmdb_info):
        """
        ????????????????????????????????????
        """
        if not path or not tmdb_info:
            return
        meta_infos = {}
        if os.path.isfile(path):
            meta_info = MetaInfo(title=os.path.basename(path))
            if meta_info.get_name():
                media_key = "[%s]%s-%s-%s" % (
                    tmdb_info.get("media_type").value, meta_info.get_name(), meta_info.year, meta_info.begin_season)
                meta_infos[media_key] = tmdb_info
        else:
            path_files = PathUtils.get_dir_files(in_path=path, exts=RMT_MEDIAEXT)
            for path_file in path_files:
                meta_info = MetaInfo(title=os.path.basename(path_file))
                if not meta_info.get_name():
                    continue
                media_key = "[%s]%s-%s-%s" % (
                    tmdb_info.get("media_type").value, meta_info.get_name(), meta_info.year, meta_info.begin_season)
                if media_key not in meta_infos.keys():
                    meta_infos[media_key] = tmdb_info
        if meta_infos:
            self.meta.update_meta_data(meta_infos)

    @staticmethod
    def merge_media_info(target, source):
        """
        ???soruce???????????????????????????target????????????
        """
        target.set_tmdb_info(source.tmdb_info)
        target.fanart_poster = source.get_poster_image()
        target.fanart_backdrop = source.get_backdrop_image()
        return target

    def get_tmdbid_by_imdbid(self, imdbid):
        """
        ??????IMDBID??????TMDB??????
        """
        if not self.find:
            return {}
        try:
            result = self.find.find_by_imdbid(imdbid) or {}
            tmdbinfo = result.get('movie_results') or result.get("tv_results")
            if tmdbinfo:
                tmdbinfo = tmdbinfo[0]
                return tmdbinfo.get("id")
        except Exception as err:
            log.console(str(err))
        return {}
