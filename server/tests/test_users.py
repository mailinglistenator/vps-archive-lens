import os
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from server.users import UserRecord, UserManager


class TestUserManager(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.storage_dir = Path(self.test_dir)
        self._orig_api_token = os.environ.pop("API_TOKEN", None)
        self._orig_user_tokens = os.environ.pop("USER_TOKENS", None)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        if self._orig_api_token is not None:
            os.environ["API_TOKEN"] = self._orig_api_token
        else:
            os.environ.pop("API_TOKEN", None)
        if self._orig_user_tokens is not None:
            os.environ["USER_TOKENS"] = self._orig_user_tokens
        else:
            os.environ.pop("USER_TOKENS", None)

    def test_default_empty_manager(self):
        manager = UserManager(storage_dir=self.storage_dir)
        self.assertEqual(len(manager.list_users()), 0)
        self.assertFalse(manager.has_users())

    def test_seed_from_api_token_env(self):
        os.environ["API_TOKEN"] = "legacy_secret_token"
        manager = UserManager(storage_dir=self.storage_dir)
        users = manager.list_users()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0].username, "admin")
        self.assertEqual(users[0].token, "legacy_secret_token")
        self.assertEqual(users[0].role, "admin")

        # Verify it persisted to users.json
        user_file = self.storage_dir / "users.json"
        self.assertTrue(user_file.is_file())

    def test_seed_from_user_tokens_env(self):
        os.environ["USER_TOKENS"] = "alice:token_alice:admin, bob:token_bob , charlie"
        manager = UserManager(storage_dir=self.storage_dir)
        users = {u.username: u for u in manager.list_users()}
        self.assertEqual(len(users), 3)

        self.assertEqual(users["alice"].role, "admin")
        self.assertEqual(users["alice"].token, "token_alice")

        self.assertEqual(users["bob"].role, "user")
        self.assertEqual(users["bob"].token, "token_bob")

        self.assertEqual(users["charlie"].role, "user")
        self.assertTrue(users["charlie"].token.startswith("lens_"))

    def test_add_and_get_user(self):
        manager = UserManager(storage_dir=self.storage_dir)
        user = manager.add_user("friend_dave", role="user")

        self.assertEqual(user.username, "friend_dave")
        self.assertEqual(user.role, "user")
        self.assertTrue(user.token.startswith("lens_"))

        # Lookup by token
        found = manager.get_user_by_token(user.token)
        self.assertIsNotNone(found)
        self.assertEqual(found.username, "friend_dave")

        # Invalid token returns None
        self.assertIsNone(manager.get_user_by_token("wrong_token"))

    def test_add_duplicate_username_raises(self):
        manager = UserManager(storage_dir=self.storage_dir)
        manager.add_user("eve", custom_token="token_eve_1")
        with self.assertRaises(ValueError):
            manager.add_user("eve", custom_token="token_eve_2")

    def test_revoke_user(self):
        manager = UserManager(storage_dir=self.storage_dir)
        u1 = manager.add_user("user1", custom_token="tok1")
        u2 = manager.add_user("user2", custom_token="tok2")

        self.assertEqual(len(manager.list_users()), 2)
        revoked = manager.revoke_user("user1")
        self.assertTrue(revoked)
        self.assertEqual(len(manager.list_users()), 1)
        self.assertIsNone(manager.get_user_by_token("tok1"))
        self.assertIsNotNone(manager.get_user_by_token("tok2"))

        # Revoking non-existent user returns False
        self.assertFalse(manager.revoke_user("nonexistent"))

    def test_persistence_across_instances(self):
        mgr1 = UserManager(storage_dir=self.storage_dir)
        mgr1.add_user("persisted_user", custom_token="secret_key_123", role="admin")

        # Create new manager pointing to same directory
        mgr2 = UserManager(storage_dir=self.storage_dir)
        user = mgr2.get_user_by_username("persisted_user")
        self.assertIsNotNone(user)
        self.assertEqual(user.token, "secret_key_123")
        self.assertEqual(user.role, "admin")


class TestFastAPIUserEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp()
        cls._orig_storage = os.environ.get("STORAGE_DIR")
        cls._orig_api_token = os.environ.get("API_TOKEN")

        os.environ["STORAGE_DIR"] = cls.test_dir
        os.environ["MEDIA_STORAGE_DIR"] = str(Path(cls.test_dir) / "videos")
        os.environ["API_TOKEN"] = "admin_super_secret"

        import server.app as app_module
        app_module.STORAGE_DIR = Path(cls.test_dir)
        app_module.IMAGE_CACHE_DIR = app_module.STORAGE_DIR / "image_cache"
        app_module.MEDIA_STORAGE_DIR = app_module.STORAGE_DIR / "videos"
        app_module.COOKIES_FILE = app_module.STORAGE_DIR / "cookies.txt"

        app_module.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        app_module.IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        app_module.MEDIA_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

        cls.app = app_module.app
        cls.user_manager = app_module.user_manager
        cls.user_manager.storage_dir = Path(cls.test_dir)
        cls.user_manager.users_file = Path(cls.test_dir) / "users.json"
        with cls.user_manager._lock:
            cls.user_manager._users.clear()
            cls.user_manager._token_to_user.clear()

        cls.user_manager.add_user("admin", custom_token="admin_super_secret", role="admin")
        cls.user_manager.add_user("friend_sam", custom_token="sam_secret_key", role="user")
        cls.client = TestClient(cls.app)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.test_dir, ignore_errors=True)
        if cls._orig_storage is not None:
            os.environ["STORAGE_DIR"] = cls._orig_storage
        else:
            os.environ.pop("STORAGE_DIR", None)

        if cls._orig_api_token is not None:
            os.environ["API_TOKEN"] = cls._orig_api_token
        else:
            os.environ.pop("API_TOKEN", None)

    def setUp(self):
        self.client.cookies.clear()

    def test_unauthenticated_dashboard_returns_login(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Login - VPS Archive Lens", res.text)
        self.assertIn('name="token"', res.text)

    def test_authenticated_dashboard_with_cookie(self):
        res = self.client.get("/", cookies={"lens_token": "sam_secret_key"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("friend_sam (user)", res.text)

    def test_authenticated_dashboard_with_query_param(self):
        res = self.client.get("/?token=sam_secret_key")
        self.assertEqual(res.status_code, 200)
        self.assertIn("friend_sam (user)", res.text)
        self.assertIn("VPS Power Hub", res.text)

    def test_authenticated_dashboard_with_bearer_header(self):
        res = self.client.get("/", headers={"Authorization": "Bearer admin_super_secret"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("admin (admin)", res.text)

    def test_admin_list_users_as_admin(self):
        res = self.client.get("/api/admin/users", headers={"Authorization": "Bearer admin_super_secret"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        usernames = [u["username"] for u in data]
        self.assertIn("admin", usernames)
        self.assertIn("friend_sam", usernames)

    def test_admin_list_users_as_regular_user_forbidden(self):
        res = self.client.get("/api/admin/users", headers={"Authorization": "Bearer sam_secret_key"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("Admin role required", res.json()["detail"])

    def test_admin_add_and_revoke_user_flow(self):
        # Admin creates new friend user
        add_res = self.client.post(
            "/api/admin/users",
            json={"username": "friend_carol", "role": "user", "token": "carol_token_999"},
            headers={"Authorization": "Bearer admin_super_secret"}
        )
        self.assertEqual(add_res.status_code, 200)
        self.assertEqual(add_res.json()["username"], "friend_carol")
        self.assertEqual(add_res.json()["token"], "carol_token_999")

        # Carol can now access dashboard
        carol_dash = self.client.get("/?token=carol_token_999")
        self.assertEqual(carol_dash.status_code, 200)
        self.assertIn("friend_carol (user)", carol_dash.text)

        # Non-admin cannot revoke
        revoke_forbidden = self.client.delete(
            "/api/admin/users/friend_carol",
            headers={"Authorization": "Bearer sam_secret_key"}
        )
        self.assertEqual(revoke_forbidden.status_code, 403)

        # Admin cannot self-revoke
        self_revoke = self.client.delete(
            "/api/admin/users/admin",
            headers={"Authorization": "Bearer admin_super_secret"}
        )
        self.assertEqual(self_revoke.status_code, 400)

        # Admin revokes carol
        revoke_res = self.client.delete(
            "/api/admin/users/friend_carol",
            headers={"Authorization": "Bearer admin_super_secret"}
        )
        self.assertEqual(revoke_res.status_code, 200)

        # Carol can no longer access
        carol_revoked = self.client.get("/?token=carol_token_999")
        self.assertEqual(carol_revoked.status_code, 401)
        self.assertIn("Invalid access token", carol_revoked.text)

    def test_push_archive_user_attribution(self):
        # Friend pushes an article snapshot
        push_res = self.client.post(
            "/archive/push",
            json={
                "html": "<html><body><h1>Multiuser Test Article</h1><p>Content</p></body></html>",
                "url": "https://news.example.com/multiuser-test",
                "title": "Multiuser Test Article"
            },
            headers={"Authorization": "Bearer sam_secret_key"}
        )
        self.assertEqual(push_res.status_code, 200)
        data = push_res.json()
        snapshot_id = data["snapshot_id"]

        # Check that .meta.json was created with user attribution
        meta_file = Path(self.test_dir) / f"{snapshot_id}.meta.json"
        self.assertTrue(meta_file.is_file())
        import json
        with open(meta_file, "r", encoding="utf-8") as mf:
            mdata = json.load(mf)
            self.assertEqual(mdata["created_by"], "friend_sam")
            self.assertEqual(mdata["title"], "Multiuser Test Article")

        # Verify raw view works publicly without auth
        raw_res = self.client.get(f"/view/{snapshot_id}")
        self.assertEqual(raw_res.status_code, 200)
        self.assertIn("Multiuser Test Article", raw_res.text)

        # Verify reader mode works publicly without auth
        reader_res = self.client.get(f"/reader/{snapshot_id}")
        self.assertEqual(reader_res.status_code, 200)
        self.assertIn("Multiuser Test Article", reader_res.text)

    def test_user_dashboard_strict_segregation(self):
        # Admin pushes an article
        admin_push = self.client.post(
            "/archive/push",
            json={
                "html": "<html><body><h1>Admin Secret Article</h1></body></html>",
                "url": "https://admin-confidential.example.com",
                "title": "Admin Secret Article"
            },
            headers={"Authorization": "Bearer admin_super_secret"}
        )
        self.assertEqual(admin_push.status_code, 200)

        # Friend Sam pushes an article
        sam_push = self.client.post(
            "/archive/push",
            json={
                "html": "<html><body><h1>Sam Personal Article</h1></body></html>",
                "url": "https://sam-interests.example.com",
                "title": "Sam Personal Article"
            },
            headers={"Authorization": "Bearer sam_secret_key"}
        )
        self.assertEqual(sam_push.status_code, 200)

        # Sam accesses dashboard
        sam_dash = self.client.get("/?token=sam_secret_key")
        self.assertEqual(sam_dash.status_code, 200)
        self.assertIn("Sam Personal Article", sam_dash.text)
        # Sam MUST NOT see Admin Secret Article in the dashboard!
        self.assertNotIn("Admin Secret Article", sam_dash.text)
        # Sam does NOT have 'All' filter button
        self.assertNotIn('id="filterAllBtn"', sam_dash.text)
        self.assertIn("My Saved Articles", sam_dash.text)

        # Admin accesses dashboard
        admin_dash = self.client.get("/?token=admin_super_secret")
        self.assertEqual(admin_dash.status_code, 200)
        # Admin can see both
        self.assertIn("Admin Secret Article", admin_dash.text)
        self.assertIn("Sam Personal Article", admin_dash.text)
        self.assertIn("filterAllBtn", admin_dash.text)

    def test_media_strict_segregation(self):
        media_dir = Path(self.test_dir) / "videos"
        media_dir.mkdir(parents=True, exist_ok=True)

        # Create admin media item
        admin_meta = {
            "id": "admin_vid_1",
            "title": "Admin Confidential Video",
            "url": "https://youtube.com/watch?v=admin1",
            "uploader": "AdminChannel",
            "duration": 120,
            "duration_str": "2:00",
            "format": "video",
            "filename": "admin_vid_1.mp4",
            "size_mb": 15.0,
            "media_type": "video/mp4",
            "thumbnail": "",
            "created_by": "admin",
            "created_at": "2026-09-09T00:00:00Z"
        }
        with open(media_dir / "admin_vid_1.json", "w", encoding="utf-8") as f:
            import json
            json.dump(admin_meta, f)
        with open(media_dir / "admin_vid_1.mp4", "w", encoding="utf-8") as f:
            f.write("mock video content")

        # Create Sam media item
        sam_meta = {
            "id": "sam_vid_1",
            "title": "Sam Favorite Music",
            "url": "https://youtube.com/watch?v=sam1",
            "uploader": "SamChannel",
            "duration": 200,
            "duration_str": "3:20",
            "format": "video",
            "filename": "sam_vid_1.mp4",
            "size_mb": 25.0,
            "media_type": "video/mp4",
            "thumbnail": "",
            "created_by": "friend_sam",
            "created_at": "2026-09-09T01:00:00Z"
        }
        with open(media_dir / "sam_vid_1.json", "w", encoding="utf-8") as f:
            json.dump(sam_meta, f)
        with open(media_dir / "sam_vid_1.mp4", "w", encoding="utf-8") as f:
            f.write("mock video content 2")

        # Sam lists media: should only see sam_vid_1
        sam_list = self.client.get("/api/media/list?token=sam_secret_key")
        self.assertEqual(sam_list.status_code, 200)
        sam_items = sam_list.json()["items"]
        sam_ids = [it["id"] for it in sam_items]
        self.assertIn("sam_vid_1", sam_ids)
        self.assertNotIn("admin_vid_1", sam_ids)

        # Admin lists media: sees both
        admin_list = self.client.get("/api/media/list?token=admin_super_secret")
        self.assertEqual(admin_list.status_code, 200)
        admin_items = admin_list.json()["items"]
        admin_ids = [it["id"] for it in admin_items]
        self.assertIn("admin_vid_1", admin_ids)
        self.assertIn("sam_vid_1", admin_ids)

        # Sam tries to stream admin's media -> 403 Forbidden
        sam_stream_admin = self.client.get("/api/media/stream/admin_vid_1?token=sam_secret_key")
        self.assertEqual(sam_stream_admin.status_code, 403)

        # Sam streams own media -> 200 OK
        sam_stream_own = self.client.get("/api/media/stream/sam_vid_1?token=sam_secret_key")
        self.assertEqual(sam_stream_own.status_code, 200)

        # Sam tries to download admin's media -> 403 Forbidden
        sam_dl_admin = self.client.get("/api/media/download/admin_vid_1?token=sam_secret_key")
        self.assertEqual(sam_dl_admin.status_code, 403)

        # Sam tries to delete admin's media -> 403 Forbidden
        sam_del_admin = self.client.delete("/api/media/admin_vid_1?token=sam_secret_key")
        self.assertEqual(sam_del_admin.status_code, 403)
        self.assertTrue((media_dir / "admin_vid_1.mp4").exists())

        # Sam cannot upload or delete cookies -> 403 Forbidden
        sam_upload_cookies = self.client.post("/api/media/cookies?token=sam_secret_key", content=b"cookies")
        self.assertEqual(sam_upload_cookies.status_code, 403)
        sam_del_cookies = self.client.delete("/api/media/cookies?token=sam_secret_key")
        self.assertEqual(sam_del_cookies.status_code, 403)

        # Sam deletes own media -> 200 OK
        sam_del_own = self.client.delete("/api/media/sam_vid_1?token=sam_secret_key")
        self.assertEqual(sam_del_own.status_code, 200)
        self.assertFalse((media_dir / "sam_vid_1.mp4").exists())


if __name__ == "__main__":
    unittest.main()
