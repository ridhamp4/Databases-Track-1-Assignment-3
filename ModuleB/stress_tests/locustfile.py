from __future__ import annotations

import threading
from itertools import cycle
from datetime import datetime, timezone

from locust import HttpUser, task, between, events
import requests


DEFAULT_USERS = [
    {"username": "admin_user", "password": "password123"},
    {"username": "laksh_jain", "password": "password123"},
    {"username": "parthiv_p", "password": "password123"},
    {"username": "ridham_p", "password": "password123"},
    {"username": "shriniket_b", "password": "password123"},
    {"username": "rudra_s", "password": "password123"},
    {"username": "prof_yogesh", "password": "password123"},
    {"username": "alumni_rahul", "password": "password123"},
]


class SharedArtifacts:
    lock = threading.Lock()
    ready = False
    post_id = None
    created_by = None
    creator_token = None


class CredentialPool:
    lock = threading.Lock()
    credentials = cycle(DEFAULT_USERS)

    @classmethod
    def next(cls):
        with cls.lock:
            return next(cls.credentials)


class ModuleBUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        self.account = CredentialPool.next()
        self.token = self.login(self.account)
        self.client.headers.update({"Authorization": f"Bearer {self.token}"})
        self.ensure_shared_artifacts()

    def login(self, account):
        response = self.client.post(
            "/api/auth/login",
            json={"username": account["username"], "password": account["password"]},
            name="/api/auth/login",
        )
        response.raise_for_status()
        return response.json()["token"]

    def ensure_shared_artifacts(self):
        if SharedArtifacts.ready:
            return
        with SharedArtifacts.lock:
            if SharedArtifacts.ready:
                return

            unique = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
            post_response = self.client.post(
                "/api/posts",
                json={"content": f"LOCUST_SHARED_POST::{unique}", "groupId": None, "imageUrl": None},
                name="/api/posts:create",
            )
            post_response.raise_for_status()
            SharedArtifacts.post_id = post_response.json()["postId"]
            SharedArtifacts.created_by = self.account["username"]
            SharedArtifacts.creator_token = self.token
            SharedArtifacts.ready = True

    @task(5)
    def comment_shared_post(self):
        self.ensure_shared_artifacts()
        response = self.client.post(
            f"/api/posts/{SharedArtifacts.post_id}/comments",
            json={"content": f"Locust comment from {self.account['username']}"},
            name="/api/posts/:id/comments",
        )
        response.raise_for_status()

    @task(1)
    def read_feed(self):
        response = self.client.get("/api/posts?feed=global", name="/api/posts")
        response.raise_for_status()

    @task(1)
    def read_polls(self):
        response = self.client.get("/api/polls/", name="/api/polls/")
        response.raise_for_status()


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    if not (SharedArtifacts.ready and SharedArtifacts.creator_token):
        return

    client = requests.Session()
    client.headers.update({"Authorization": f"Bearer {SharedArtifacts.creator_token}"})
    if SharedArtifacts.post_id is not None:
        client.delete(f"{environment.host}/api/posts/{SharedArtifacts.post_id}")
