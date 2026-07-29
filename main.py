from __future__ import annotations

import argparse
import math
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from playwright.sync_api import Page, sync_playwright


LOGIN_PHONE_ENV = "VIDEO_MONITOR_LOGIN_PHONE"
LOGIN_PASSWORD_ENV = "VIDEO_MONITOR_LOGIN_PASSWORD"
BARK_URL_ENV = "VIDEO_MONITOR_BARK_URL"
DEFAULT_LOGIN_PHONE_SELECTOR = (
    "input[name='phone'], input[name='uname'], input[name='username'], input[name='account'], "
    "input[id='phone'], input[id='uname'], input[id='username'], input[id='account'], "
    "input[type='tel'], input[placeholder*='手机号'], input[placeholder*='手机'], "
    "input[placeholder*='账号']"
)
DEFAULT_LOGIN_PASSWORD_SELECTOR = (
    "input[type='password'], input[name='password'], input[name='pwd'], "
    "input[id='password'], input[id='pwd']"
)
DEFAULT_LOGIN_SUBMIT_SELECTOR = (
    "#loginBtn, #login, .loginBtn, .btn-login, .login-button, "
    "button[type='submit'], input[type='submit']"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Open a URL and monitor video playback state.")
    parser.add_argument("--url", required=True, help="URL to open.")
    parser.add_argument(
        "--browser-channel",
        default="msedge",
        choices=["chrome", "msedge"],
        help="Installed browser channel to launch.",
    )
    parser.add_argument(
        "--monitor-interval",
        type=float,
        default=2.0,
        help="Seconds between video status checks.",
    )
    parser.add_argument(
        "--auto-play",
        action="store_true",
        help="Attempt to play detected video elements.",
    )
    parser.add_argument(
        "--mute-before-auto-play",
        action="store_true",
        help="Mute videos before auto-play to satisfy browser autoplay policies.",
    )
    parser.add_argument(
        "--play-sequential",
        action="store_true",
        help="With --auto-play, play one video at a time and start the next after the current one ends.",
    )
    parser.add_argument(
        "--next-selector",
        help=(
            "CSS selector to click after all detected videos finish or no videos are found, "
            "for example '#prevNextFocusNext'."
        ),
    )
    parser.add_argument(
        "--no-video-next-delay",
        type=float,
        default=3.0,
        help="Seconds to wait before clicking --next-selector when no video elements are detected.",
    )
    parser.add_argument(
        "--playback-rate",
        type=float,
        help="Set detected videos to this native playback rate, for example 2 for double speed.",
    )
    parser.add_argument(
        "--auto-login",
        action="store_true",
        help=f"Fill and submit a detected login form using {LOGIN_PHONE_ENV} and {LOGIN_PASSWORD_ENV}.",
    )
    parser.add_argument(
        "--login-phone-selector",
        default=DEFAULT_LOGIN_PHONE_SELECTOR,
        help="CSS selector for the phone/account input used by --auto-login.",
    )
    parser.add_argument(
        "--login-password-selector",
        default=DEFAULT_LOGIN_PASSWORD_SELECTOR,
        help="CSS selector for the password input used by --auto-login.",
    )
    parser.add_argument(
        "--login-submit-selector",
        default=DEFAULT_LOGIN_SUBMIT_SELECTOR,
        help="CSS selector for the login submit button used by --auto-login.",
    )
    parser.add_argument(
        "--login-retry-interval",
        type=float,
        default=8.0,
        help="Seconds between auto-login attempts while a login form remains visible.",
    )
    parser.add_argument(
        "--bark-url",
        help=f"Bark push key or endpoint. It can also be supplied through {BARK_URL_ENV}.",
    )
    parser.add_argument(
        "--notify-section-complete",
        action="store_true",
        help="Send a Bark notification after each section's videos complete.",
    )
    parser.add_argument(
        "--notify-all-complete",
        action="store_true",
        help="Send a Bark notification when all videos appear to be complete.",
    )
    args = parser.parse_args()
    if args.monitor_interval <= 0:
        parser.error("--monitor-interval must be greater than 0.")
    if args.no_video_next_delay < 0:
        parser.error("--no-video-next-delay must be 0 or greater.")
    if args.playback_rate is not None and args.playback_rate <= 0:
        parser.error("--playback-rate must be greater than 0.")
    if args.login_retry_interval < 0:
        parser.error("--login-retry-interval must be 0 or greater.")
    if args.play_sequential and not args.auto_play:
        parser.error("--play-sequential requires --auto-play.")
    if (
        args.notify_section_complete or args.notify_all_complete
    ) and not (args.bark_url or os.getenv(BARK_URL_ENV)):
        parser.error(f"Bark notifications require --bark-url or {BARK_URL_ENV}.")

    return args


def collect_video_statuses(page: Page) -> list[dict[str, Any]]:
    videos: list[dict[str, Any]] = []

    for frame_index, frame in enumerate(page.frames):
        try:
            frame_videos = frame.evaluate(
                """
                () => Array.from(document.querySelectorAll("video")).map((video, index) => {
                  const rect = video.getBoundingClientRect();
                  const playState = video.ended ? "ended" : (video.paused ? "paused" : "playing");
                  return {
                    index,
                    id: video.id || null,
                    className: video.className || null,
                    playState,
                    currentTime: Number.isFinite(video.currentTime) ? video.currentTime : null,
                    duration: Number.isFinite(video.duration) ? video.duration : null,
                    paused: video.paused,
                    ended: video.ended,
                    muted: video.muted,
                    volume: video.volume,
                    playbackRate: video.playbackRate,
                    readyState: video.readyState,
                    networkState: video.networkState,
                    src: video.currentSrc || video.getAttribute("src") || null,
                    width: Math.round(rect.width),
                    height: Math.round(rect.height),
                    visible: rect.width > 0 && rect.height > 0,
                  };
                })
                """
            )
        except Exception:
            continue

        for video in frame_videos:
            video["frameIndex"] = frame_index
            video["frameName"] = frame.name
            video["frameUrl"] = frame.url
            videos.append(video)

    return videos


def format_seconds(value: Any) -> str:
    if value is None:
        return "unknown"
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return "unknown"
    return f"{value:.1f}s"


def video_signature(videos: list[dict[str, Any]]) -> tuple[Any, ...]:
    return tuple(
        (
            video.get("frameIndex"),
            video.get("index"),
            video.get("playState"),
            round(video.get("currentTime") or 0, 1),
            video.get("duration"),
            video.get("muted"),
            video.get("volume"),
            video.get("playbackRate"),
            video.get("readyState"),
            video.get("networkState"),
            video.get("visible"),
            video.get("width"),
            video.get("height"),
            video.get("src"),
        )
        for video in videos
    )


def attempt_auto_login(
    page: Page,
    phone: str | None,
    password: str | None,
    phone_selector: str,
    password_selector: str,
    submit_selector: str,
) -> dict[str, Any]:
    if not phone or not password:
        return {
            "action": "skipped",
            "errorName": "MissingCredentials",
            "errorMessage": f"{LOGIN_PHONE_ENV} and {LOGIN_PASSWORD_ENV} are required.",
        }

    for frame_index, frame in enumerate(page.frames):
        try:
            result = frame.evaluate(
                """
                ({ phone, password, phoneSelector, passwordSelector, submitSelector }) => {
                  const isVisible = (element) => {
                    if (!element) {
                      return false;
                    }
                    const rect = element.getBoundingClientRect();
                    const style = window.getComputedStyle(element);
                    return (
                      rect.width > 0 &&
                      rect.height > 0 &&
                      style.display !== "none" &&
                      style.visibility !== "hidden"
                    );
                  };

                  const firstVisible = (selector) => {
                    try {
                      return Array.from(document.querySelectorAll(selector)).find(isVisible) || null;
                    } catch (error) {
                      return null;
                    }
                  };

                  const setValue = (element, value) => {
                    const descriptor = Object.getOwnPropertyDescriptor(
                      Object.getPrototypeOf(element),
                      "value"
                    );
                    if (descriptor && descriptor.set) {
                      descriptor.set.call(element, value);
                    } else {
                      element.value = value;
                    }
                    element.dispatchEvent(new Event("input", { bubbles: true }));
                    element.dispatchEvent(new Event("change", { bubbles: true }));
                  };

                  const phoneInput = firstVisible(phoneSelector);
                  const passwordInput = firstVisible(passwordSelector);
                  if (!phoneInput || !passwordInput) {
                    return { action: "not-found" };
                  }

                  setValue(phoneInput, phone);
                  setValue(passwordInput, password);

                  let submitButton = firstVisible(submitSelector);
                  if (!submitButton) {
                    submitButton = Array.from(
                      document.querySelectorAll("button, input[type='button'], input[type='submit'], a, div[role='button']")
                    ).find((element) => {
                      if (!isVisible(element)) {
                        return false;
                      }
                      const text = `${element.textContent || ""} ${element.value || ""}`.trim();
                      return /登录|登\\s*录|login|sign\\s*in/i.test(text);
                    }) || null;
                  }

                  if (!submitButton) {
                    return {
                      action: "failed",
                      errorName: "SubmitButtonNotFound",
                      errorMessage: "Login fields were found, but no visible submit button matched.",
                    };
                  }

                  submitButton.scrollIntoView({ block: "center", inline: "center" });
                  submitButton.click();

                  return {
                    action: "clicked-login",
                    phoneSelectorMatched: phoneInput.tagName,
                    submitTagName: submitButton.tagName,
                    submitId: submitButton.id || null,
                    submitText: (submitButton.textContent || submitButton.value || "").trim().replace(/\\s+/g, " "),
                  };
                }
                """,
                {
                    "phone": phone,
                    "password": password,
                    "phoneSelector": phone_selector,
                    "passwordSelector": password_selector,
                    "submitSelector": submit_selector,
                },
            )
        except Exception as exc:
            result = {
                "action": "failed",
                "errorName": type(exc).__name__,
                "errorMessage": str(exc),
            }

        result["frameIndex"] = frame_index
        result["frameName"] = frame.name
        result["frameUrl"] = frame.url
        if result.get("action") in {"clicked-login", "failed"}:
            if result.get("action") == "clicked-login":
                try:
                    page.wait_for_load_state("load", timeout=8000)
                except Exception:
                    pass
            return result

    return {"action": "not-found"}


def login_signature(result: dict[str, Any]) -> tuple[Any, ...]:
    return (
        result.get("action"),
        result.get("frameIndex"),
        result.get("frameUrl"),
        result.get("submitId"),
        result.get("submitText"),
        result.get("errorName"),
        result.get("errorMessage"),
    )


def print_login_result(result: dict[str, Any]) -> None:
    action = result.get("action")
    if action == "not-found":
        return

    timestamp = time.strftime("%H:%M:%S")
    print(f"\n[{timestamp}] Auto-login result")
    print(f"  action={action} frame#{result.get('frameIndex')}")
    if action == "clicked-login":
        print(
            "  "
            f"submit={result.get('submitTagName')} "
            f"id={result.get('submitId')} "
            f"text={result.get('submitText') or ''}"
        )
        print(f"    frame: {result.get('frameUrl')}")
    else:
        print(f"    error: {result.get('errorName')}: {result.get('errorMessage')}")


def normalize_bark_url(value: str | None) -> str | None:
    if not value:
        return None

    value = value.strip().rstrip("/")
    if not value:
        return None

    if value.startswith(("http://", "https://")):
        return value

    return f"https://api.day.app/{urllib.parse.quote(value.strip('/'), safe='')}"


def build_bark_push_url(bark_url: str, title: str, body: str) -> str:
    parsed = urllib.parse.urlsplit(bark_url.rstrip("/"))
    path = (
        f"{parsed.path.rstrip('/')}/"
        f"{urllib.parse.quote(title, safe='')}/"
        f"{urllib.parse.quote(body, safe='')}"
    )
    query = parsed.query
    archive_query = urllib.parse.urlencode({"isArchive": "1"})
    if query:
        query = f"{query}&{archive_query}"
    else:
        query = archive_query

    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, path, query, parsed.fragment)
    )


def truncate_text(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."


def page_summary(page: Page) -> str:
    title = ""
    try:
        title = page.title().strip()
    except Exception:
        pass

    url = truncate_text(page.url, 240)
    if title:
        return f"{title}\n{url}"
    return url


def send_bark_notification(
    bark_url: str | None,
    title: str,
    body: str,
) -> dict[str, Any]:
    normalized_url = normalize_bark_url(bark_url)
    if not normalized_url:
        return {
            "action": "skipped",
            "errorName": "MissingBarkUrl",
            "errorMessage": f"{BARK_URL_ENV} is required.",
        }

    push_url = build_bark_push_url(normalized_url, title, truncate_text(body, 1200))
    request = urllib.request.Request(
        push_url,
        headers={"User-Agent": "video-monitor/1.0"},
    )

    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            response.read(1024)
            return {
                "action": "sent",
                "statusCode": response.status,
                "title": title,
            }
    except urllib.error.HTTPError as exc:
        return {
            "action": "failed",
            "statusCode": exc.code,
            "title": title,
            "errorName": type(exc).__name__,
            "errorMessage": str(exc),
        }
    except Exception as exc:
        return {
            "action": "failed",
            "title": title,
            "errorName": type(exc).__name__,
            "errorMessage": str(exc),
        }


def print_notification_result(result: dict[str, Any]) -> None:
    timestamp = time.strftime("%H:%M:%S")
    action = result.get("action")
    print(f"\n[{timestamp}] Bark notification result")
    print(
        "  "
        f"action={action} "
        f"title={result.get('title') or ''} "
        f"statusCode={result.get('statusCode') or ''}"
    )
    if action == "failed":
        print(f"    error: {result.get('errorName')}: {result.get('errorMessage')}")


def set_playback_rates(page: Page, playback_rate: float) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for frame_index, frame in enumerate(page.frames):
        try:
            frame_results = frame.evaluate(
                """
                (playbackRate) => Array.from(document.querySelectorAll("video")).map((video, index) => {
                  const src = video.currentSrc || video.getAttribute("src") || null;
                  const before = video.playbackRate;

                  try {
                    video.defaultPlaybackRate = playbackRate;
                    video.playbackRate = playbackRate;

                    return {
                      index,
                      src,
                      action: Math.abs(before - video.playbackRate) < 0.01 ? "already-rate" : "rate-set",
                      playbackRateBefore: before,
                      playbackRateAfter: video.playbackRate,
                    };
                  } catch (error) {
                    return {
                      index,
                      src,
                      action: "failed",
                      playbackRateBefore: before,
                      playbackRateAfter: video.playbackRate,
                      errorName: error && error.name ? error.name : "Error",
                      errorMessage: error && error.message ? error.message : String(error),
                    };
                  }
                })
                """,
                playback_rate,
            )
        except Exception as exc:
            frame_results = [
                {
                    "action": "failed",
                    "errorName": type(exc).__name__,
                    "errorMessage": str(exc),
                }
            ]

        for result in frame_results:
            result["frameIndex"] = frame_index
            result["frameName"] = frame.name
            result["frameUrl"] = frame.url
            results.append(result)

    return results


def playback_rate_signature(results: list[dict[str, Any]]) -> tuple[Any, ...]:
    return tuple(
        (
            result.get("frameIndex"),
            result.get("index"),
            result.get("src"),
            result.get("action"),
            result.get("playbackRateAfter"),
            result.get("errorName"),
            result.get("errorMessage"),
        )
        for result in results
    )


def print_playback_rate_results(results: list[dict[str, Any]], playback_rate: float) -> None:
    actionable_results = [
        result
        for result in results
        if result.get("action") != "already-rate"
    ]
    if not actionable_results:
        return

    timestamp = time.strftime("%H:%M:%S")
    print(f"\n[{timestamp}] Playback rate result(s), target={playback_rate:g}x")
    for result in actionable_results:
        action = result.get("action")
        print(
            "  "
            f"video#{result.get('index')} "
            f"frame#{result.get('frameIndex')} "
            f"action={action} "
            f"rateBefore={result.get('playbackRateBefore')} "
            f"rateAfter={result.get('playbackRateAfter')}"
        )
        if action == "failed":
            print(f"    error: {result.get('errorName')}: {result.get('errorMessage')}")
        print(f"    frame: {result.get('frameUrl')}")
        print(f"    src: {result.get('src') or 'no src'}")


def is_video_complete(video: dict[str, Any]) -> bool:
    if video.get("ended", False):
        return True

    current_time = video.get("currentTime")
    duration = video.get("duration")
    if not isinstance(current_time, (int, float)):
        return False
    if not isinstance(duration, (int, float)):
        return False
    if not math.isfinite(current_time) or not math.isfinite(duration):
        return False
    if duration <= 0:
        return False

    return current_time >= duration - 0.5


def completed_videos_signature(page: Page, videos: list[dict[str, Any]]) -> tuple[Any, ...] | None:
    visible_videos = [video for video in videos if video.get("visible", False)]
    relevant_videos = visible_videos or videos

    if not relevant_videos:
        return None
    if not all(is_video_complete(video) for video in relevant_videos):
        return None

    return (
        page.url,
        tuple(
            (
                video.get("frameIndex"),
                video.get("index"),
                video.get("src"),
                round(video.get("currentTime") or 0, 1),
                video.get("duration"),
            )
            for video in relevant_videos
        ),
    )


def completed_video_entries(videos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    visible_videos = [video for video in videos if video.get("visible", False)]
    relevant_videos = visible_videos or videos
    return [video for video in relevant_videos if is_video_complete(video)]


def video_completion_key(page: Page, video: dict[str, Any]) -> tuple[Any, ...]:
    return (
        page.url,
        video.get("frameUrl"),
        video.get("frameIndex"),
        video.get("index"),
        video.get("src"),
        video.get("duration"),
    )


def click_next_selector(page: Page, selector: str) -> dict[str, Any]:
    last_error: str | None = None

    for frame_index, frame in enumerate(page.frames):
        try:
            result = frame.evaluate(
                """
                (selector) => {
                  const element = document.querySelector(selector);
                  if (!element) {
                    return { action: "not-found" };
                  }

                  const rect = element.getBoundingClientRect();
                  const style = window.getComputedStyle(element);
                  const disabled =
                    element.matches("[disabled], [aria-disabled='true']") ||
                    element.classList.contains("disabled");

                  if (disabled) {
                    return { action: "disabled" };
                  }
                  if (style.display === "none" || style.visibility === "hidden") {
                    return { action: "hidden" };
                  }
                  if (rect.width <= 0 || rect.height <= 0) {
                    return { action: "empty-box" };
                  }

                  element.scrollIntoView({ block: "center", inline: "center" });
                  element.click();

                  return {
                    action: "clicked-next",
                    tagName: element.tagName,
                    id: element.id || null,
                    className: element.className || null,
                    text: (element.textContent || "").trim().replace(/\\s+/g, " "),
                  };
                }
                """,
                selector,
            )
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            continue

        result["frameIndex"] = frame_index
        result["frameName"] = frame.name
        result["frameUrl"] = frame.url
        if result.get("action") == "clicked-next":
            return result

    return {
        "action": "failed",
        "selector": selector,
        "errorName": "NextSelectorNotClicked",
        "errorMessage": last_error or f"No visible enabled element matched {selector!r}.",
    }


def print_next_click_result(result: dict[str, Any], selector: str) -> None:
    timestamp = time.strftime("%H:%M:%S")
    action = result.get("action")

    print(f"\n[{timestamp}] Next selector result")
    print(f"  selector={selector} action={action}")
    if action == "clicked-next":
        print(
            "  "
            f"element={result.get('tagName')} "
            f"id={result.get('id')} "
            f"text={result.get('text') or ''}"
        )
        print(f"    frame: {result.get('frameUrl')}")
    else:
        print(f"    error: {result.get('errorName')}: {result.get('errorMessage')}")


def play_video_in_frame(
    page: Page,
    frame_index: int,
    video_index: int,
    mute_before_auto_play: bool,
) -> list[dict[str, Any]]:
    try:
        frame = page.frames[frame_index]
    except IndexError:
        return [
            {
                "frameIndex": frame_index,
                "index": video_index,
                "action": "failed",
                "errorName": "FrameNotFoundError",
                "errorMessage": f"Frame #{frame_index} no longer exists.",
            }
        ]

    try:
        result = frame.evaluate(
            """
            async ({ videoIndex, muteBeforeAutoPlay }) => {
              const video = document.querySelectorAll("video")[videoIndex];
              if (!video) {
                return {
                  index: videoIndex,
                  src: null,
                  action: "failed",
                  errorName: "VideoNotFoundError",
                  errorMessage: `Video #${videoIndex} no longer exists.`,
                };
              }

              const src = video.currentSrc || video.getAttribute("src") || null;

              if (video.ended) {
                return {
                  index: videoIndex,
                  src,
                  action: "skipped-ended",
                  pausedAfter: video.paused,
                  mutedAfter: video.muted,
                };
              }

              if (!video.paused) {
                return {
                  index: videoIndex,
                  src,
                  action: "already-playing",
                  pausedAfter: false,
                  mutedAfter: video.muted,
                };
              }

              try {
                if (muteBeforeAutoPlay) {
                  video.muted = true;
                }

                await Promise.race([
                  Promise.resolve(video.play()),
                  new Promise((_, reject) => {
                    setTimeout(() => reject(new Error("play() timed out")), 3000);
                  }),
                ]);

                return {
                  index: videoIndex,
                  src,
                  action: video.paused ? "play-requested" : "played",
                  pausedAfter: video.paused,
                  mutedAfter: video.muted,
                };
              } catch (error) {
                return {
                  index: videoIndex,
                  src,
                  action: "failed",
                  pausedAfter: video.paused,
                  mutedAfter: video.muted,
                  errorName: error && error.name ? error.name : "Error",
                  errorMessage: error && error.message ? error.message : String(error),
                };
              }
            }
            """,
            {"videoIndex": video_index, "muteBeforeAutoPlay": mute_before_auto_play},
        )
    except Exception as exc:
        result = {
            "index": video_index,
            "action": "failed",
            "errorName": type(exc).__name__,
            "errorMessage": str(exc),
        }

    result["frameIndex"] = frame_index
    result["frameName"] = frame.name
    result["frameUrl"] = frame.url
    return [result]


def auto_play_next_video(page: Page, mute_before_auto_play: bool) -> list[dict[str, Any]]:
    videos = collect_video_statuses(page)
    has_playing_video = any(
        not video.get("paused", True) and not video.get("ended", False)
        for video in videos
    )
    if has_playing_video:
        return []

    for video in videos:
        if video.get("ended", False):
            continue
        if not video.get("paused", True):
            continue

        return play_video_in_frame(
            page,
            int(video["frameIndex"]),
            int(video["index"]),
            mute_before_auto_play,
        )

    return []


def auto_play_videos(page: Page, mute_before_auto_play: bool) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for frame_index, frame in enumerate(page.frames):
        try:
            frame_results = frame.evaluate(
                """
                async ({ muteBeforeAutoPlay }) => {
                  const videos = Array.from(document.querySelectorAll("video"));
                  const results = [];

                  for (const [index, video] of videos.entries()) {
                    const src = video.currentSrc || video.getAttribute("src") || null;

                    if (video.ended) {
                      results.push({
                        index,
                        src,
                        action: "skipped-ended",
                        pausedAfter: video.paused,
                        mutedAfter: video.muted,
                      });
                      continue;
                    }

                    if (!video.paused) {
                      results.push({
                        index,
                        src,
                        action: "already-playing",
                        pausedAfter: false,
                        mutedAfter: video.muted,
                      });
                      continue;
                    }

                    try {
                      if (muteBeforeAutoPlay) {
                        video.muted = true;
                      }

                      await Promise.race([
                        Promise.resolve(video.play()),
                        new Promise((_, reject) => {
                          setTimeout(() => reject(new Error("play() timed out")), 3000);
                        }),
                      ]);

                      results.push({
                        index,
                        src,
                        action: video.paused ? "play-requested" : "played",
                        pausedAfter: video.paused,
                        mutedAfter: video.muted,
                      });
                    } catch (error) {
                      results.push({
                        index,
                        src,
                        action: "failed",
                        pausedAfter: video.paused,
                        mutedAfter: video.muted,
                        errorName: error && error.name ? error.name : "Error",
                        errorMessage: error && error.message ? error.message : String(error),
                      });
                    }
                  }

                  return results;
                }
                """,
                {"muteBeforeAutoPlay": mute_before_auto_play},
            )
        except Exception as exc:
            frame_results = [
                {
                    "action": "failed",
                    "errorName": type(exc).__name__,
                    "errorMessage": str(exc),
                }
            ]

        for result in frame_results:
            result["frameIndex"] = frame_index
            result["frameName"] = frame.name
            result["frameUrl"] = frame.url
            results.append(result)

    return results


def auto_play_signature(results: list[dict[str, Any]]) -> tuple[Any, ...]:
    return tuple(
        (
            result.get("frameIndex"),
            result.get("index"),
            result.get("src"),
            result.get("action"),
            result.get("pausedAfter"),
            result.get("mutedAfter"),
            result.get("errorName"),
            result.get("errorMessage"),
        )
        for result in results
    )


def print_auto_play_results(results: list[dict[str, Any]]) -> None:
    actionable_results = [
        result
        for result in results
        if result.get("action") not in {"already-playing", "skipped-ended"}
    ]
    if not actionable_results:
        return

    timestamp = time.strftime("%H:%M:%S")
    print(f"\n[{timestamp}] Auto-play attempt result(s)")
    for result in actionable_results:
        action = result.get("action")
        print(
            "  "
            f"video#{result.get('index')} "
            f"frame#{result.get('frameIndex')} "
            f"action={action} "
            f"pausedAfter={result.get('pausedAfter')} "
            f"mutedAfter={result.get('mutedAfter')}"
        )
        if action == "failed":
            print(f"    error: {result.get('errorName')}: {result.get('errorMessage')}")
        print(f"    frame: {result.get('frameUrl')}")
        print(f"    src: {result.get('src') or 'no src'}")


def print_video_statuses(videos: list[dict[str, Any]]) -> None:
    timestamp = time.strftime("%H:%M:%S")
    print(f"\n[{timestamp}] Detected {len(videos)} video element(s)")

    for video in videos:
        current_time = format_seconds(video.get("currentTime"))
        duration = format_seconds(video.get("duration"))
        size = f"{video.get('width')}x{video.get('height')}"
        src = video.get("src") or "no src"

        print(
            "  "
            f"video#{video.get('index')} "
            f"frame#{video.get('frameIndex')} "
            f"state={video.get('playState')} "
            f"time={current_time}/{duration} "
            f"readyState={video.get('readyState')} "
            f"networkState={video.get('networkState')} "
            f"muted={video.get('muted')} "
            f"volume={video.get('volume')} "
            f"rate={video.get('playbackRate')} "
            f"visible={video.get('visible')} "
            f"size={size}"
        )
        print(f"    frame: {video.get('frameUrl')}")
        print(f"    src: {src}")


def pause_videos(page: Page) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for frame_index, frame in enumerate(page.frames):
        try:
            frame_results = frame.evaluate(
                """
                () => Array.from(document.querySelectorAll("video")).map((video, index) => {
                  const src = video.currentSrc || video.getAttribute("src") || null;

                  if (video.ended) {
                    return {
                      index,
                      src,
                      action: "skipped-ended",
                      pausedAfter: video.paused,
                      mutedAfter: video.muted,
                    };
                  }

                  if (video.paused) {
                    return {
                      index,
                      src,
                      action: "already-paused",
                      pausedAfter: true,
                      mutedAfter: video.muted,
                    };
                  }

                  try {
                    video.dataset.codexPausedByTool = "1";
                    video.pause();
                    return {
                      index,
                      src,
                      action: "paused",
                      pausedAfter: video.paused,
                      mutedAfter: video.muted,
                    };
                  } catch (error) {
                    return {
                      index,
                      src,
                      action: "failed",
                      pausedAfter: video.paused,
                      mutedAfter: video.muted,
                      errorName: error && error.name ? error.name : "Error",
                      errorMessage: error && error.message ? error.message : String(error),
                    };
                  }
                })
                """
            )
        except Exception as exc:
            frame_results = [
                {
                    "action": "failed",
                    "errorName": type(exc).__name__,
                    "errorMessage": str(exc),
                }
            ]

        for result in frame_results:
            result["frameIndex"] = frame_index
            result["frameName"] = frame.name
            result["frameUrl"] = frame.url
            results.append(result)

    return results


def resume_videos(page: Page) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for frame_index, frame in enumerate(page.frames):
        try:
            frame_results = frame.evaluate(
                """
                async () => {
                  const videos = Array.from(document.querySelectorAll("video"));
                  const results = [];

                  for (const [index, video] of videos.entries()) {
                    const src = video.currentSrc || video.getAttribute("src") || null;

                    if (video.dataset.codexPausedByTool !== "1") {
                      results.push({
                        index,
                        src,
                        action: "skipped-not-marked",
                        pausedAfter: video.paused,
                        mutedAfter: video.muted,
                      });
                      continue;
                    }

                    delete video.dataset.codexPausedByTool;

                    try {
                      await Promise.race([
                        Promise.resolve(video.play()),
                        new Promise((_, reject) => {
                          setTimeout(() => reject(new Error("play() timed out")), 3000);
                        }),
                      ]);

                      results.push({
                        index,
                        src,
                        action: video.paused ? "play-requested" : "resumed",
                        pausedAfter: video.paused,
                        mutedAfter: video.muted,
                      });
                    } catch (error) {
                      results.push({
                        index,
                        src,
                        action: "failed",
                        pausedAfter: video.paused,
                        mutedAfter: video.muted,
                        errorName: error && error.name ? error.name : "Error",
                        errorMessage: error && error.message ? error.message : String(error),
                      });
                    }
                  }

                  return results;
                }
                """
            )
        except Exception as exc:
            frame_results = [
                {
                    "action": "failed",
                    "errorName": type(exc).__name__,
                    "errorMessage": str(exc),
                }
            ]

        for result in frame_results:
            result["frameIndex"] = frame_index
            result["frameName"] = frame.name
            result["frameUrl"] = frame.url
            results.append(result)

    return results


def video_transition_signature(results: list[dict[str, Any]]) -> tuple[Any, ...]:
    return tuple(
        (
            result.get("frameIndex"),
            result.get("index"),
            result.get("src"),
            result.get("action"),
            result.get("pausedAfter"),
            result.get("mutedAfter"),
            result.get("errorName"),
            result.get("errorMessage"),
        )
        for result in results
    )


def print_video_transition_results(title: str, results: list[dict[str, Any]]) -> None:
    actionable_results = [
        result
        for result in results
        if result.get("action")
        not in {"already-paused", "skipped-ended", "skipped-not-marked"}
    ]
    if not actionable_results:
        return

    timestamp = time.strftime("%H:%M:%S")
    print(f"\n[{timestamp}] {title}")
    for result in actionable_results:
        action = result.get("action")
        print(
            "  "
            f"video#{result.get('index')} "
            f"frame#{result.get('frameIndex')} "
            f"action={action} "
            f"pausedAfter={result.get('pausedAfter')} "
            f"mutedAfter={result.get('mutedAfter')}"
        )
        if action == "failed":
            print(f"    error: {result.get('errorName')}: {result.get('errorMessage')}")
        print(f"    frame: {result.get('frameUrl')}")
        print(f"    src: {result.get('src') or 'no src'}")


def read_control_commands(stop_event: threading.Event, pause_event: threading.Event) -> None:
    if sys.stdin.isatty():
        print("Type pause, resume, or press Enter to stop.")

    while not stop_event.is_set():
        try:
            command = input().strip().lower()
        except EOFError:
            print("No interactive input detected, closing the browser.")
            stop_event.set()
            break

        if command in {"", "stop", "quit", "exit"}:
            stop_event.set()
            break
        if command in {"pause", "p"}:
            if not pause_event.is_set():
                pause_event.set()
                print("Pause requested.")
            continue
        if command in {"resume", "continue", "r"}:
            if pause_event.is_set():
                pause_event.clear()
                print("Resume requested.")
            continue

        print(f"Unknown command: {command}")


def monitor_videos(
    page: Page,
    stop_event: threading.Event,
    pause_event: threading.Event,
    interval: float,
    auto_play: bool,
    mute_before_auto_play: bool,
    play_sequential: bool,
    next_selector: str | None,
    no_video_next_delay: float,
    playback_rate: float | None,
    auto_login: bool,
    login_phone: str | None,
    login_password: str | None,
    login_phone_selector: str,
    login_password_selector: str,
    login_submit_selector: str,
    login_retry_interval: float,
    bark_url: str | None,
    notify_section_complete: bool,
    notify_all_complete: bool,
) -> None:
    last_signature: tuple[Any, ...] | None = None
    last_auto_play_signature: tuple[Any, ...] | None = None
    last_next_click_signature: tuple[Any, ...] | None = None
    last_playback_rate_signature: tuple[Any, ...] | None = None
    last_login_signature: tuple[Any, ...] | None = None
    completed_video_keys: set[tuple[Any, ...]] = set()
    last_login_attempt_at = 0.0
    completed_video_count = 0
    all_complete_notification_sent = False
    pause_applied = False
    no_video_since: float | None = None

    def keep_paused() -> bool:
        nonlocal pause_applied

        if not pause_event.is_set():
            return False

        pause_results = pause_videos(page)
        print_video_transition_results("Pause video result(s)", pause_results)
        if not pause_applied:
            print("Video monitor paused. Automation is suspended.")
            pause_applied = True
        return True

    def mark_completed_videos(videos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        nonlocal completed_video_count

        newly_completed: list[dict[str, Any]] = []
        for video in completed_video_entries(videos):
            key = video_completion_key(page, video)
            if key in completed_video_keys:
                continue

            completed_video_keys.add(key)
            completed_video_count += 1
            video_with_number = dict(video)
            video_with_number["completedVideoNumber"] = completed_video_count
            newly_completed.append(video_with_number)

        return newly_completed

    def send_section_complete_notification(video: dict[str, Any]) -> None:
        title = "视频控制台：本节视频已完成"
        current_time = format_seconds(video.get("currentTime"))
        duration = format_seconds(video.get("duration"))
        body = (
            f"第 {video.get('completedVideoNumber')} 个视频已看完。\n"
            f"video#{video.get('index')} frame#{video.get('frameIndex')} "
            f"time={current_time}/{duration}\n"
            f"{page_summary(page)}"
        )
        result = send_bark_notification(bark_url, title, body)
        print_notification_result(result)

    def send_all_complete_notification(reason: str) -> None:
        nonlocal all_complete_notification_sent

        if all_complete_notification_sent:
            return

        title = "视频控制台：全部视频已完成"
        body = (
            f"全部视频已看完。已完成 {completed_video_count} 个视频。\n"
            f"{reason}\n"
            f"{page_summary(page)}"
        )
        result = send_bark_notification(bark_url, title, body)
        print_notification_result(result)
        all_complete_notification_sent = True

    if auto_login and auto_play and play_sequential and next_selector and playback_rate is not None:
        print("Video monitor started. Auto-login, sequential auto-play, playback-rate, and next-click are enabled.")
    elif auto_play and play_sequential and next_selector and playback_rate is not None:
        print("Video monitor started. Sequential auto-play, playback-rate, and next-click are enabled.")
    elif auto_play and play_sequential and next_selector:
        print("Video monitor started. Sequential auto-play and next-click are enabled.")
    elif auto_play and play_sequential:
        print("Video monitor started. Sequential auto-play is enabled for detected video elements.")
    elif auto_play:
        print("Video monitor started. Auto-play is enabled for detected video elements.")
    elif playback_rate is not None and next_selector:
        print("Video monitor started. Playback-rate and next-click are enabled.")
    elif playback_rate is not None:
        print("Video monitor started. Playback-rate control is enabled for detected video elements.")
    elif next_selector:
        print("Video monitor started. Next-click is enabled after videos finish or no video is detected.")
    else:
        print("Video monitor started. This only reads video state and does not control playback.")

    while True:
        try:
            if page.is_closed():
                stop_event.set()
                break

            if keep_paused():
                if stop_event.wait(interval):
                    break
                continue

            if pause_applied:
                resume_results = resume_videos(page)
                print_video_transition_results("Resume video result(s)", resume_results)
                print("Video monitor resumed. Automation is active.")
                pause_applied = False

            current_time = time.monotonic()
            if auto_login and current_time - last_login_attempt_at >= login_retry_interval:
                login_result = attempt_auto_login(
                    page,
                    login_phone,
                    login_password,
                    login_phone_selector,
                    login_password_selector,
                    login_submit_selector,
                )
                signature = login_signature(login_result)
                if login_result.get("action") != "not-found" and signature != last_login_signature:
                    print_login_result(login_result)
                last_login_signature = signature
                if login_result.get("action") in {"clicked-login", "failed"}:
                    last_login_attempt_at = current_time
                if login_result.get("action") == "clicked-login":
                    if keep_paused():
                        continue
                    continue

            if keep_paused():
                continue

            if playback_rate is not None:
                playback_rate_results = set_playback_rates(page, playback_rate)
                signature = playback_rate_signature(playback_rate_results)
                if playback_rate_results and signature != last_playback_rate_signature:
                    print_playback_rate_results(playback_rate_results, playback_rate)
                last_playback_rate_signature = signature

            if keep_paused():
                continue

            if auto_play:
                if play_sequential:
                    auto_play_results = auto_play_next_video(page, mute_before_auto_play)
                else:
                    auto_play_results = auto_play_videos(page, mute_before_auto_play)
                signature = auto_play_signature(auto_play_results)
                if auto_play_results and signature != last_auto_play_signature:
                    print_auto_play_results(auto_play_results)
                last_auto_play_signature = signature

            if keep_paused():
                continue

            videos = collect_video_statuses(page)
            signature = video_signature(videos)
            current_time = time.monotonic()

            if videos and signature != last_signature:
                print_video_statuses(videos)
            elif not videos and last_signature != ():
                print("No video elements detected yet.")

            last_signature = signature

            if keep_paused():
                continue

            newly_completed_videos = mark_completed_videos(videos)
            if notify_section_complete:
                for completed_video in newly_completed_videos:
                    send_section_complete_notification(completed_video)

            completion_signature = completed_videos_signature(page, videos)
            if next_selector:
                if (
                    completion_signature is not None
                    and completion_signature != last_next_click_signature
                ):
                    next_click_result = click_next_selector(page, next_selector)
                    print_next_click_result(next_click_result, next_selector)
                    if (
                        notify_all_complete
                        and next_click_result.get("action") != "clicked-next"
                    ):
                        send_all_complete_notification("下一节按钮不存在或不可点击。")
                    last_next_click_signature = completion_signature
                elif completion_signature is None:
                    last_next_click_signature = None

                if videos:
                    no_video_since = None
                else:
                    if no_video_since is None:
                        no_video_since = current_time

                    if current_time - no_video_since >= no_video_next_delay:
                        next_click_result = click_next_selector(page, next_selector)
                        if next_click_result.get("action") == "clicked-next":
                            print_next_click_result(next_click_result, next_selector)
                            no_video_since = None
                        else:
                            if notify_all_complete and completed_video_count > 0:
                                send_all_complete_notification("当前页面没有视频，且下一节按钮不可点击。")
                            no_video_since = current_time
            elif notify_all_complete and completion_signature is not None:
                send_all_complete_notification("未配置下一节按钮。")
        except Exception as exc:
            print(f"Video monitor error: {exc}")

        if stop_event.wait(interval):
            break


def main() -> None:
    args = parse_args()
    login_phone = os.getenv(LOGIN_PHONE_ENV)
    login_password = os.getenv(LOGIN_PASSWORD_ENV)
    bark_url = args.bark_url or os.getenv(BARK_URL_ENV)

    with sync_playwright() as p:
        launch_options = {"headless": False, "channel": args.browser_channel}

        browser = p.chromium.launch(**launch_options)
        page = browser.new_page()
        page.goto(args.url, wait_until="load")

        print(f"Opened URL: {page.url}")
        if args.auto_login:
            login_result = attempt_auto_login(
                page,
                login_phone,
                login_password,
                args.login_phone_selector,
                args.login_password_selector,
                args.login_submit_selector,
            )
            print_login_result(login_result)
        stop_event = threading.Event()
        pause_event = threading.Event()
        control_thread = threading.Thread(
            target=read_control_commands,
            args=(stop_event, pause_event),
            daemon=True,
        )
        control_thread.start()

        try:
            monitor_videos(
                page,
                stop_event,
                pause_event,
                args.monitor_interval,
                args.auto_play,
                args.mute_before_auto_play,
                args.play_sequential,
                args.next_selector,
                args.no_video_next_delay,
                args.playback_rate,
                args.auto_login,
                login_phone,
                login_password,
                args.login_phone_selector,
                args.login_password_selector,
                args.login_submit_selector,
                args.login_retry_interval,
                bark_url,
                args.notify_section_complete,
                args.notify_all_complete,
            )
        except KeyboardInterrupt:
            print("\nStopping video monitor.")
            stop_event.set()

        browser.close()


if __name__ == "__main__":
    main()
