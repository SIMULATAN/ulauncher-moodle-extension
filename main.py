import datetime
import json
import logging
import re

from requests import post
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.client.Extension import Extension
from ulauncher.api.shared.action.DoNothingAction import DoNothingAction
from ulauncher.api.shared.action.OpenUrlAction import OpenUrlAction
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.SetUserQueryAction import SetUserQueryAction
from ulauncher.api.shared.event import KeywordQueryEvent, PreferencesUpdateEvent, PreferencesEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem

from cachetools import TTLCache, cached, keys

logger = logging.getLogger(__name__)
REST_SERVER = "/webservice/rest/server.php"

cache = TTLCache(maxsize=100, ttl=60)


@cached(cache=cache)
def get_service(fname, token, url, **kwargs):
    """
    :param fname: function for request
    :param token: user token
    :return: dictionary/list containing the result of the query
    """
    req_params = kwargs
    logger.debug("req_params: " + str(req_params))
    req_params.update({"wstoken": token, 'moodlewsrestformat': 'json',
                       "wsfunction": fname})
    response = post(url + REST_SERVER, req_params)
    response = response.json()
    return response


class MoodleEvents(Extension):
    """
    A class for fetching and displaying moodle upcoming events
    """

    def __init__(self):
        super(MoodleEvents, self).__init__()
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())
        self.subscribe(PreferencesUpdateEvent, PreferencesUpdateEventListener())
        self.subscribe(PreferencesEvent, PreferencesUpdateEventListener())

    def show_menu(self, keyword):
        """
        Show the main extension menu,
        when the user types the extension keyword without arguments
        """

        return RenderResultListAction([
            ExtensionResultItem(icon='images/icon.png',
                                name="Upcoming events",
                                description="Access your profile page",
                                on_enter=SetUserQueryAction("%s events " %
                                                            keyword)),
            ExtensionResultItem(icon='images/icon.png',
                                name="courses",
                                description="Courses",
                                on_enter=SetUserQueryAction("%s courses " %
                                                            keyword))
        ])

    def events(self, query):
        logger.debug("in events")
        site = self.preferences['site']
        token = self.preferences['token']
        data = get_service('core_calendar_get_calendar_upcoming_view',
                           token, site)
        if "exception" in data:
            return RenderResultListAction(
                [ExtensionResultItem(icon='images/icon.png',
                                     name=data["message"],
                                     on_enter=DoNothingAction(
                                     ))])
        items = []
        for event in data['events']:
            try:
                var = event['action']
                is_done = False
            except KeyError:
                # if anmu event is done there is no "add asset" action
                is_done = True
            # convert epoch time to readable
            time = datetime.datetime.fromtimestamp(event['timestart']).strftime("%d/%m/%y, %H:%M")
            # TODO handle idn and url better?
            try:
                idn = event['course']['id']
            except:
                idn = ''
            try:
                url = event['url']
            except:
                url = ''
            name = event['name']
            if name:
                # the name sometimes has a trailing dot
                name = name.rstrip(".")
            if not search(query, name):
                continue
            items.append((ExtensionResultItem(icon='images/' + ("tick" if is_done else "cross") + '.png',
                                              name=f"{idn} - {name}:   {time}",
                                              description=("Done" if is_done else "Not done") + " | Full Name: " + name,
                                              on_enter=OpenUrlAction(url)), event['timestart']))
        # Sort by time
        items.sort(key=lambda x: x[1])
        items = [x[0] for x in items]
        if not items:
            items.append(ExtensionResultItem(icon='images/icon.png',
                                             name="Nothing to Show",
                                             highlightable=False,
                                             on_enter=DoNothingAction()))

        return RenderResultListAction(items)

    def courses(self, query):
        logger.debug("in courses")
        site = self.preferences['site']
        token = self.preferences['token']
        starred = self.preferences['courses_type'] == "Starred"
        logger.error(self.preferences['course_status'])
        data = get_service(
            'core_course_get_enrolled_courses_by_timeline_classification',
            token, site, classification=self.preferences['course_status'])

        if "exception" in data:
            return RenderResultListAction(
                [ExtensionResultItem(icon='images/icon.png',
                                     name=data["message"],
                                     on_enter=DoNothingAction(
                                     ))])
        items = []
        for course in data['courses']:
            if not search(query,  course['fullname']):
                continue
            if starred and course["isfavourite"] is False:
                continue
            items.append(ExtensionResultItem(icon='images/icon.png',
                                             name=f"{course['fullname']}",
                                             description=f"Category: {course['coursecategory']}",
                                             on_enter=OpenUrlAction(course['viewurl'])))
        if not items:
            items.append(ExtensionResultItem(icon='images/icon.png',
                                             name="Nothing to Show",
                                             highlightable=False,
                                             on_enter=DoNothingAction()))

        return RenderResultListAction(items)


class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):

        query = event.get_argument() or ""
        keyword = event.get_keyword()
        kw_fuctions = {extension.preferences["kw_events"]: extension.events, 
                       extension.preferences["kw_courses"]: extension.courses}
        if keyword in kw_fuctions:
            return kw_fuctions[keyword](query)

        if not query:
            return extension.show_menu(keyword)

        # Get the action based on the search terms
        events = re.findall(r"^events(.*)?$", query, re.IGNORECASE)
        courses = re.findall(r"^courses(.*)?$", query, re.IGNORECASE)

        try:

            if events:
                return extension.events(events[0].strip())

            if courses:
                return extension.courses(courses[0].strip())
        except Exception as e:
            logger.info(str(e))

        return extension.show_menu(keyword)


class PreferencesUpdateEventListener(EventListener):

    def on_event(self, event, extension):
        logger.debug("Got new preferences: %s" % (json.dumps(event.preferences) if hasattr(event, "preferences") else event.__dict__))

def search(query, text):
    if not query:
        return True
    query = query.lower()
    text = text.lower()
    return [True if q not in text for q in query.split(" ") else False]


if __name__ == '__main__':
    MoodleEvents().run()
