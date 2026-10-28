#!/usr/bin/env python3
"""Compatibility wrapper for radar.pipeline.profile and radar.sinks.rss_sink."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from radar.pipeline.freshness import FreshnessStage
from radar.pipeline.profile import evaluate_profile as evaluate_profile_match
from radar.sinks.rss_sink import RssSink


def generate_rss_feed(jobs, output_path="feed.xml"):
    RssSink().export(jobs, {"feed_path": output_path})
