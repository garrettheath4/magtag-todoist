import time
import binascii

import board
import digitalio
import displayio
import terminalio
import wifi

from adafruit_datetime import datetime, timezone
from rtc import RTC
import adafruit_logging as logging
from neopixel import NeoPixel
from adafruit_display_text import label
from my_secrets import my_secrets


LOGGING_LEVEL = logging.DEBUG
TODOIST_TASKS_URL = "https://api.todoist.com/api/v1/tasks/filter?limit=200&query=today"
WORLD_TIME_API_BASE = "https://time.now/developer/api/timezone/"
MAX_TASKS_ON_SCREEN = 8
AUTO_REFRESH_SECONDS = 10 * 60
GMAIL_ATOM_FEED_URL = "https://mail.google.com/mail/feed/atom"

last_display_refresh = 0
_requests_session = None
time_set_from_internet = False

# A task with a due time, such as "14:00", will show its due time instead of its priority
TASK_PRIORITY_SYMBOLS = ["    *", "   **", "  ***", " ****"]


class NeoPixelDimmer(NeoPixel):
    """
    Keeps track of how bright or dim a pixel should be after brightening or dimming it in step increments.
    Use `npd.brighter()` and `npd.dimmer()` to adjust the brightness.
    """
    def brighter(self):
        self.brightness = min(self.brightness + 0.1, 1.0)

    def dimmer(self):
        self.brightness = max(self.brightness - 0.1, 0.0)

    def fill_white(self):
        self.fill((255,) * 3)
    
    def fill_blue(self):
        self.fill((0, 0, 255))


def setup_button(pin):
    button = digitalio.DigitalInOut(pin)
    button.direction = digitalio.Direction.INPUT
    button.pull = digitalio.Pull.UP
    return button


def setup_pixels():
    return NeoPixelDimmer(board.NEOPIXEL, 4, brightness=0.10, auto_write=True)


def get_display_text_labels():
    """
    Create the two text areas using displayio so we don't depend on
    adafruit_magtag.graphics expecting `display.root_group`.
    """

    display = board.DISPLAY
    time.sleep(display.time_to_refresh)

    main_group = displayio.Group()

    tasks_label = label.Label(
        terminalio.FONT,
        text="",
        color=0x000000,
        background_color=0xFFFFFF,
        padding_top=4,
        padding_bottom=3,
        padding_right=4,
        padding_left=8,
        scale=1,
    )
    tasks_label.x = 8
    tasks_label.y = 10
    try:
        tasks_label.line_spacing = 1.0
    except AttributeError:
        pass

    updated_label = label.Label(
        terminalio.FONT,
        text="",
        color=0x000000,
        background_color=0xFFFFFF,
        padding_top=1,
        padding_bottom=2,
        padding_right=7,
        padding_left=4,
        scale=1,
    )
    updated_label.x = 122
    updated_label.y = 120
    try:
        updated_label.line_spacing = 1.0
    except AttributeError:
        pass

    email_label = label.Label(
        terminalio.FONT,
        text="",
        color=0x000000,
        background_color=0xFFFFFF,
        padding_top=1,
        padding_bottom=2,
        padding_right=4,
        padding_left=8,
        scale=1,
    )
    email_label.x = 8
    email_label.y = 120
    try:
        email_label.line_spacing = 1.0
    except AttributeError:
        pass

    main_group.append(tasks_label)
    main_group.append(email_label)
    main_group.append(updated_label)

    # Newer firmware uses root_group; older firmware may only support show().
    try:
        display.root_group = main_group
    except AttributeError:
        logger.debug("display.root_group not supported, using display.show()")
        if hasattr(display, "show"):
            try:
                display.show(main_group)
            except TypeError:
                display.show()

    return display, tasks_label, updated_label, email_label


def ensure_requests_session():
    logger = get_logger("wifi")
    import adafruit_requests

    global _requests_session
    if _requests_session is not None:
        return _requests_session

    # Connect to WiFi if needed.
    # Let errors bubble up to the firmware so you get the full stack trace.
    logger.debug("Connecting to WiFi...")
    wifi.radio.connect(my_secrets["ssid"], my_secrets["password"])
    logger.info("Connected to WiFi network %s (password %d chars)", my_secrets["ssid"], len(my_secrets["password"]))

    # Wait for IPv4 address (best-effort; attribute may vary by firmware).
    start = time.monotonic()
    while True:
        try:
            ip = wifi.radio.ipv4_address
        except AttributeError:
            ip = "1.1.1.1"

        if ip:
            break
        if time.monotonic() - start > 15:
            raise RuntimeError("Wifi connect timeout")
        time.sleep(0.2)

    # Work around `adafruit_connection_manager.get_radio_socketpool()` failing with:
    # `TypeError: unsupported type for __hash__: 'SocketPool'`
    #
    # Your firmware/library combo produces an unhashable SocketPool instance.
    # `adafruit_requests` stores the socket pool in dicts keyed by the pool object,
    # so we wrap it in a proxy that defines `__hash__`.
    import socketpool
    import ssl

    class _HashableSocketPoolProxy:
        def __init__(self, inner):
            self._inner = inner

        def __hash__(self):
            return id(self._inner)

        def __getattr__(self, name):
            return getattr(self._inner, name)

    pool = socketpool.SocketPool(wifi.radio)
    ssl_context = ssl.create_default_context()
    _requests_session = adafruit_requests.Session(_HashableSocketPoolProxy(pool), ssl_context)
    return _requests_session


def get_today_iso_date(requests_session):
    logger = get_logger("time")
    timezone_str = my_secrets["timezone"]
    logger.debug("Fetching current datetime for timezone %s", timezone_str)
    response = requests_session.get(WORLD_TIME_API_BASE + timezone_str)
    now_payload = response.json()
    response.close()
    # "datetime": "2026-03-23T13:52:53.285572-04:00"
    datetime_str = now_payload["datetime"].replace("T", " ").split(".", 1)[0]
    # datetime_str = "2026-03-23 13:52:53"
    logger.debug("Current datetime: %s", datetime_str)
    global time_set_from_internet
    if not time_set_from_internet:
        day_of_week = now_payload["day_of_week"]
        day_of_year = now_payload["day_of_year"]
        dst = int(now_payload["dst"])
        # time.struct_time(tuple items as ints) = (tm_year, tm_mon, tm_mday, tm_hour, tm_min, tm_sec, tm_wday, tm_yday, tm_isdst)
        struct_time_str = datetime_str.replace("-", " ").replace(":", " ").split(" ") + [day_of_week, day_of_year, dst]
        struct_time_int = [int(x) for x in struct_time_str]
        global rtc
        rtc.datetime = time.struct_time(struct_time_int)
        logger.debug("RTC time set. The timestamp on these logs should now reflect the new, correct time.")
        time_set_from_internet = True
    return datetime_str


def fetch_due_today_tasks(requests_session):
    logger = get_logger("todo")
    headers = {"Authorization": "Bearer " + my_secrets["todoist_api_key"]}
    all_tasks = []
    next_url = TODOIST_TASKS_URL

    while next_url:
        logger.debug("Fetching tasks from %s", next_url)
        response = requests_session.get(next_url, headers=headers)
        payload = response.json()
        response.close()

        # Newer Todoist endpoint returns {"results": [...], "next_cursor": "..."}.
        if isinstance(payload, dict):
            message = payload.get("message") or payload.get("error")
            if message:
                raise RuntimeError("Todoist API returned error payload: " + str(message))

            results = payload.get("results")
            if not isinstance(results, list):
                keys = sorted(payload.keys())
                raise RuntimeError(
                    "Todoist API payload missing list 'results' (keys: {})".format(
                        ",".join(keys)
                    )
                )
            #logger.debug("Tasks results: %s", results)  # verbose
            all_tasks.extend(results)

            next_cursor = payload.get("next_cursor", None)
            if next_cursor:
                logger.debug("More tasks to fetch. Next cursor: %s", next_cursor)
                next_url = TODOIST_TASKS_URL + "&cursor=" + str(next_cursor)
                continue
            break

        # Back-compat fallback if endpoint returns a bare list.
        if isinstance(payload, list):
            logger.warning("Todoist API payload is a list, not a dict")
            all_tasks.extend(payload)
            break

        raise TypeError("Todoist API payload must be dict or list, got " + str(type(payload)))

    logger.info("Tasks due today: %d", len(all_tasks))
    return all_tasks


def prioritize_tasks(tasks):
    """
    Example task:
    {
        'updated_at': '2026-03-23T02:53:57.653726Z',
        'parent_id': None,
        'project_id': '6Crg37qgRr7Wq9RV',
        'priority': 3,
        'labels': ['every-week', 'mobile'],
        'duration': None,
        'is_collapsed': False,
        'added_at': '2025-08-21T19:06:18.236800Z',
        'responsible_uid': None,
        'id': '6ch5cmCpHfCCJJP3',
        'is_deleted': False,
        'completed_at': None,
        'note_count': 0,
        'goal_ids': [],
        'completed_by_uid': None,
        'deadline': None,
        'assigned_by_uid': None,
        'checked': False,
        'added_by_uid': '5042555',
        'section_id': '6683GWF7CQJPR6XV',
        'user_id': '5042555',
        'child_order': 20,
        'description': '',
        'due': {
            'timezone': 'America/New_York'  # OR `None` for floating time (local time zone)
            'lang': 'en',
            'is_recurring': True,
            'string': 'every sun',
            'date': '2026-03-23'  # OR '2026-03-23T09:52:00'
        },
        'content': 'Go grocery shopping',
        'day_order': -1
    }
    """
    logger = get_logger("todo")
    logger.debug("Prioritizing %d tasks", len(tasks))
    if not isinstance(tasks, list):
        raise TypeError("tasks must be list, got " + str(type(tasks)))

    # Todoist priority is 1..4 where 4 is highest.
    return sorted(
        tasks,
        key=lambda t: (
            -int(t.get("priority", 1)),
            t.get("due", {}).get("datetime") or t.get("due", {}).get("date") or "",
            t.get("content", "").lower(),
        ),
    )


def promote_earliest_time_task(tasks):
    """
    Given a list of tasks, returns a list of tasks where the first task is the task with the earliest due time and the
    remainder of the list are the remaining tasks (without the earliest due time task). If no timed tasks exist in the
    given list of tasks, the original list of tasks will be returned, unaltered.
    """
    if not tasks:
        return tasks
    due_time_tasks = list(filter(lambda t: type(t) == dict and "T" in t["due"]["date"], tasks))
    if not due_time_tasks:
        return tasks
    due_time_tasks_sorted = sorted(
        due_time_tasks,
        key=lambda t: (
            t.get("due", {}).get("datetime") or t.get("due", {}).get("date") or "",
            -int(t.get("priority", 1)),
            t.get("content", "").lower(),
        ),
    )
    earliest_task = due_time_tasks_sorted[0]
    return [earliest_task] + [t for t in tasks if t["id"] != earliest_task["id"]]


def ascii_only(text):
    """
    Keep codepoints U+0000..U+007E; terminalio cannot render arbitrary Unicode.
    Note that ordinal character 127 is filtered out too since it is the `Delete` character (a meta-character).
    """
    return "".join(ch for ch in text if ord(ch) < 127)


def utc_due_iso_to_local_hhmm(utc_str):
    logger = get_logger("todo")
    s = utc_str.strip()
    if not s:
        logger.error("Unable to parse UTC string: %s", utc_str)
        return "??:??"
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)  # aware, offset from UTC
    secs = int(dt.timestamp())
    loc = time.localtime(secs)
    return "{:02d}:{:02d}".format(loc.tm_hour, loc.tm_min)


def _make_gmail_basic_auth_header(username, password):
    credentials = "{}:{}".format(username, password)
    encoded = binascii.b2a_base64(credentials.encode("utf-8")).decode("utf-8").strip()
    return "Basic " + encoded


def fetch_unread_gmail_count(requests_session):
    logger = get_logger("mail")
    headers = {
        "Authorization": _make_gmail_basic_auth_header(
            my_secrets["email_gmail_address"],
            my_secrets["email_gmail_password"],
        )
    }
    logger.debug("Fetching unread Gmail count...")
    response = requests_session.get(GMAIL_ATOM_FEED_URL, headers=headers)
    if response.status_code != 200:
        raise RuntimeError(f"Expected status code 200 from Gmail Atom feed request but received: {response.status_code}")
    atom_feed = response.text
    response.close()
    #logger.debug("Atom feed: %s", atom_feed)  # verbose

    open_tag = "<fullcount>"
    close_tag = "</fullcount>"
    start = atom_feed.find(open_tag)
    end = atom_feed.find(close_tag)
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError("Gmail atom feed missing fullcount")

    count_text = atom_feed[start + len(open_tag):end].strip()
    logger.info("Unread Gmail messages: %s", count_text)
    return int(count_text)


def build_display_text(tasks):
    logger = get_logger("disp")
    if not tasks or type(tasks) != list:
        if type(tasks) != list:
            logger.warning("Tasks is not a list, got %s", type(tasks))
        return "No tasks due today."

    logger.debug("Building display text for %d tasks (of %d)", min(len(tasks), MAX_TASKS_ON_SCREEN), len(tasks))
    # Text in lines must be ASCII only, not Unicode.
    lines = []
    for task in tasks[:MAX_TASKS_ON_SCREEN]:
        due_date_str = task['due']['date']
        if 'T' in due_date_str:
            # task.due.date == '2026-03-23T14:00:00Z'
            if task['due']['timezone'] == None and due_date_str.endswith("Z"):
                # Due time is a Floating Time, meaning it is already in the local time zone
                prefix = due_date_str[11:16]
            else:
                prefix = utc_due_iso_to_local_hhmm(due_date_str)
        else:
            priority = int(task.get("priority", 1))
            prefix = TASK_PRIORITY_SYMBOLS[priority - 1]
        raw = task.get("content", "").strip()
        content = ascii_only(raw).strip() or "(Untitled task)"
        lines.append("{} {}".format(prefix, content))
    return "\n".join(lines)


def safe_refresh_display(display):
    """
    MagTag / e-paper refresh can raise `RuntimeError: Refresh too soon`
    if called before the driver cooldown expires. Retry in that case.
    """
    logger = get_logger("disp")

    global last_display_refresh

    # Best-effort: respect our own successful refresh timestamp first.
    now = time.monotonic()
    min_wait = display.time_to_refresh - (now - last_display_refresh)
    if min_wait > 0:
        time.sleep(min_wait)

    for _ in range(3):
        try:
            logger.debug("Refreshing display...")
            display.refresh()
            logger.debug("Display refreshed")
            last_display_refresh = time.monotonic()
            return
        except RuntimeError as error:
            if "Refresh too soon" in str(error):
                logger.debug("Refresh too soon, sleeping for %d seconds...", display.time_to_refresh)
                time.sleep(display.time_to_refresh)
                continue
            raise


def refresh_tasks(display, tasks_label, updated_label, email_label, pixels: NeoPixelDimmer):
    global last_display_refresh
    pixels.fill_blue()  # Blue: working
    requests_session = ensure_requests_session()
    datetime = get_today_iso_date(requests_session)
    tasks = fetch_due_today_tasks(requests_session)
    tasks = prioritize_tasks(tasks)
    tasks = promote_earliest_time_task(tasks)

    tasks_label.text = build_display_text(tasks)
    updated_label.text = "Updated: " + datetime

    if 'email_gmail_address' in my_secrets and 'email_gmail_password' in my_secrets:
        unread_emails = fetch_unread_gmail_count(requests_session)
        email_label.text = "Emails: {}".format(unread_emails)
    else:
        email_label.text = ""  # hides text box

    safe_refresh_display(display)
    pixels.fill_white()  # White: idle


_all_loggers = {}


def get_logger(name: str):
    if name in _all_loggers:
        return _all_loggers[name]
    new_logger = logging.getLogger(name)
    new_logger.setLevel(LOGGING_LEVEL)
    print_handler = logging.StreamHandler()
    new_logger.addHandler(print_handler)
    formatter = logging.Formatter(fmt="%(asctime)s %(levelname)-5s [%(name)s] %(message)s")
    print_handler.setFormatter(formatter)
    _all_loggers[name] = new_logger
    return new_logger


def main():
    global rtc
    rtc = RTC()
    #__match_args__: Final = ("tm_year", "tm_mon", "tm_mday", "tm_hour", "tm_min", "tm_sec", "tm_wday", "tm_yday", "tm_isdst")
    rtc.datetime = time.struct_time((2026, 1, 1, 00, 00, 00, 3, 1, -4))  # Set placeholder time until time is fetched

    logger = get_logger("MAIN")
    logger.info("Starting magtag-todoist")

    display, tasks_label, updated_label, email_label = get_display_text_labels()
    last_display_refresh = time.monotonic()
    pixels = setup_pixels()

    button_a = setup_button(board.BUTTON_A)  # manual refresh
    button_b = setup_button(board.BUTTON_B)  # brightness down
    button_c = setup_button(board.BUTTON_C)  # brightness up
    button_d = setup_button(board.BUTTON_D)  # manual refresh alt

    class _DummyMagTag:
        def add_text(self, *args, **kwargs):
            # No-op: we render via displayio labels instead.
            pass


    magtag = _DummyMagTag()

    magtag.add_text(
        text_position=(8, 10),
        line_spacing=0.9,
        text_scale=1,
    )
    magtag.add_text(
        text_position=(8, 108),
        line_spacing=0.8,
        text_scale=1,
    )

    refresh_tasks(display, tasks_label, updated_label, email_label, pixels)
    last_refresh = time.monotonic()
    last_a = button_a.value
    last_b = button_b.value
    last_c = button_c.value
    last_d = button_d.value

    while True:
        now = time.monotonic()
        if now - last_refresh >= AUTO_REFRESH_SECONDS:
            refresh_tasks(display, tasks_label, updated_label, email_label, pixels)
            last_refresh = now

        a = button_a.value
        b = button_b.value
        c = button_c.value
        d = button_d.value

        if last_a and not a:
            refresh_tasks(display, tasks_label, updated_label, email_label, pixels)  # A: manual refresh
            last_refresh = time.monotonic()
        elif last_b and not b:
            pixels.dimmer()
        elif last_c and not c:
            pixels.brighter()
        elif last_d and not d:
            refresh_tasks(display, tasks_label, updated_label, email_label, pixels)  # D: alternate refresh button
            last_refresh = time.monotonic()

        last_a = a
        last_b = b
        last_c = c
        last_d = d
        time.sleep(0.1)


main()
