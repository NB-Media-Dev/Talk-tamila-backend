# API map

Every endpoint, the handler that serves it, and the service method it calls.
Regenerate with `python scripts/api_map.py --markdown`.


## app/admin/routes.py

| Method | Path | Handler | Service method |
|---|---|---|---|
| GET | `/api/v1/admin/stories` | `get_all_stories` (30) | AdminService.get_all_stories (app/admin/services.py:87) |
| POST | `/api/v1/admin/stories` | `create_story` (52) | StoryCreationService.create_story (app/common/services/story/story_creation_service.py:41) |
| GET | `/api/v1/admin/stories/stats` | `get_platform_story_stats` (62) | AdminService.get_platform_story_stats (app/admin/services.py:40) |
| GET | `/api/v1/admin/stories/my` | `get_my_stories_with_metrics` (70) | StoryFeedService.get_my_stories_with_metrics (app/common/services/story/story_feed_service.py:480) |
| GET | `/api/v1/admin/stories/my/stats` | `get_my_story_stats` (78) | StoryAnalyticsService.get_my_story_stats (app/common/services/story/story_analytics_service.py:210) |
| GET | `/api/v1/admin/stories/reports` | `get_story_reports` (86) | AdminService.get_story_reports (app/admin/services.py:163) |
| DELETE | `/api/v1/admin/stories/{story_id:int}` | `delete_story` (96) | AdminService.delete_story (app/admin/services.py:227) |
| PATCH | `/api/v1/admin/stories/{story_id:int}/restore` | `restore_story` (105) | AdminService.restore_story (app/admin/services.py:237) |
| PATCH | `/api/v1/admin/users/{user_id:int}/ban` | `ban_user` (115) | AdminService.ban_user (app/admin/services.py:247) |
| POST | `/api/v1/admin/users/{user_id:int}/ban` | `ban_user` (115) | AdminService.ban_user (app/admin/services.py:247) |
| PATCH | `/api/v1/admin/users/{user_id:int}/unban` | `unban_user` (125) | AdminService.unban_user (app/admin/services.py:261) |
| POST | `/api/v1/admin/users/{user_id:int}/unban` | `unban_user` (125) | AdminService.unban_user (app/admin/services.py:261) |
| POST | `/api/v1/admin/stories/{story_id:int}/warn` | `warn_story_creator` (134) | AdminService.warn_story_creator (app/admin/services.py:270) |
| POST | `/api/v1/admin/users/{user_id:int}/warn` | `warn_user` (152) | AdminService.warn_user (app/admin/services.py:325) |

## app/auth/routes.py

| Method | Path | Handler | Service method |
|---|---|---|---|
| GET | `/api/v1/auth/check-availability` | `check_availability` (39) | AuthService.check_availability (app/common/services/auth_service.py:274) |
| POST | `/api/v1/auth/signup` | `signup` (49) | AuthService.signup (app/common/services/auth_service.py:303) |
| POST | `/api/v1/auth/login` | `login` (69) | AuthService.login (app/common/services/auth_service.py:318) |
| POST | `/api/v1/auth/refresh` | `refresh_token` (77) | AuthService.refresh_token (app/common/services/auth_service.py:362) |
| GET | `/api/v1/auth/profile` | `get_my_profile` (83) | ProfileService.get_my_profile (app/common/services/profile_service.py:33) |
| PUT | `/api/v1/auth/profile` | `update_my_profile` (91) | ProfileService.update_my_profile (app/common/services/profile_service.py:41) |
| POST | `/api/v1/auth/change-password/request-otp` | `request_change_password_otp` (110) | AuthService.request_change_password_otp (app/common/services/auth_service.py:106) |
| POST | `/api/v1/auth/change-password` | `change_password` (119) | AuthService.change_password (app/common/services/auth_service.py:139) |
| POST | `/api/v1/auth/forgot-password` | `forgot_password` (129) | AuthService.forgot_password (app/common/services/auth_service.py:73) |
| POST | `/api/v1/auth/verify-otp` | `verify_otp` (140) | AuthService.verify_otp (app/common/services/auth_service.py:182) |
| POST | `/api/v1/auth/reset-password` | `reset_password` (146) | AuthService.reset_password (app/common/services/auth_service.py:191) |

## app/freelancer/routes.py

| Method | Path | Handler | Service method |
|---|---|---|---|
| GET | `/api/v1/freelancer/stats` | `get_freelancer_stats` (15) | StoryAnalyticsService.get_my_story_stats (app/common/services/story/story_analytics_service.py:210) |
| GET | `/api/v1/freelancer/stories` | `get_freelancer_stories` (29) | StoryFeedService.get_my_stories_with_metrics (app/common/services/story/story_feed_service.py:480) |
| GET | `/api/v1/freelancer/stories/stats` | `get_freelancer_story_stats` (37) | StoryAnalyticsService.get_my_story_stats (app/common/services/story/story_analytics_service.py:210) |

## app/influencer/routes.py

| Method | Path | Handler | Service method |
|---|---|---|---|
| GET | `/api/v1/influencer/stats` | `get_dashboard_stats` (16) | InfluencerService.get_dashboard_stats (app/influencer/services.py:9) |
| GET | `/api/v1/influencer/stories` | `get_influencer_stories` (23) | StoryFeedService.get_my_stories_with_metrics (app/common/services/story/story_feed_service.py:480) |
| GET | `/api/v1/influencer/stories/stats` | `get_influencer_story_stats` (31) | StoryAnalyticsService.get_my_story_stats (app/common/services/story/story_analytics_service.py:210) |

## app/message/routes.py

| Method | Path | Handler | Service method |
|---|---|---|---|
| GET | `/api/v1/messages/summary` | `get_summary` (35) | MessageService.get_summary (app/common/services/message_service.py:294) |
| GET | `/api/v1/messages/conversations` | `list_conversations` (41) | MessageService.list_conversations (app/common/services/message_service.py:325) |
| GET | `/api/v1/messages/users` | `search_people` (50) | MessageService.search_people (app/common/services/message_service.py:776) |
| GET | `/api/v1/messages/thread/{user_id}` | `get_thread` (62) | MessageService.get_thread (app/common/services/message_service.py:401) |
| POST | `/api/v1/messages/thread/{user_id}` | `send_message` (77) | MessageService.send_message (app/common/services/message_service.py:495)<br>PushService.notify_new_message (app/common/services/push_service.py:130) |
| POST | `/api/v1/messages/thread/{user_id}/read` | `mark_thread_read` (90) | MessageService.mark_thread_read (app/common/services/message_service.py:642) |
| POST | `/api/v1/messages/thread/{user_id}/unread` | `mark_thread_unread` (99) | MessageService.mark_thread_unread (app/common/services/message_service.py:659) |
| POST | `/api/v1/messages/thread/{user_id}/accept` | `accept_message_request` (108) | MessageService.accept_message_request (app/common/services/message_service.py:211) |
| DELETE | `/api/v1/messages/thread/{user_id}` | `delete_thread` (117) | MessageService.delete_thread (app/common/services/message_service.py:575) |
| POST | `/api/v1/messages/thread/{user_id}/block` | `block_user` (126) | MessageService.block_user (app/common/services/message_service.py:590) |
| DELETE | `/api/v1/messages/thread/{user_id}/block` | `unblock_user` (135) | MessageService.unblock_user (app/common/services/message_service.py:606) |
| POST | `/api/v1/messages/thread/{user_id}/mute` | `mute_chat` (143) | MessageService.mute_chat (app/common/services/message_service.py:616) |
| DELETE | `/api/v1/messages/thread/{user_id}/mute` | `unmute_chat` (152) | MessageService.unmute_chat (app/common/services/message_service.py:627) |
| POST | `/api/v1/messages/thread/{user_id}/report` | `report_user` (160) | MessageService.report_user (app/common/services/message_service.py:635) |
| PUT | `/api/v1/messages/{message_id}/reaction` | `react_to_message` (169) | MessageService.react_to_message (app/common/services/message_service.py:738) |
| DELETE | `/api/v1/messages/{message_id}/reaction` | `remove_message_reaction` (179) | MessageService.remove_message_reaction (app/common/services/message_service.py:762) |
| DELETE | `/api/v1/messages/{message_id}` | `unsend_message` (187) | MessageService.unsend_message (app/common/services/message_service.py:534) |
| GET | `/api/v1/messages/push/public-key` | `push_public_key` (196) | PushService.push_public_key (app/common/services/push_service.py:86) |
| POST | `/api/v1/messages/push/subscribe` | `push_subscribe` (200) | PushService.push_subscribe (app/common/services/push_service.py:94) |
| POST | `/api/v1/messages/push/unsubscribe` | `push_unsubscribe` (209) | PushService.push_unsubscribe (app/common/services/push_service.py:124) |

## app/notification/routes.py

| Method | Path | Handler | Service method |
|---|---|---|---|
| GET | `/api/v1/notifications` | `get_notifications` (15) | NotificationService.get_notifications (app/common/services/notification_service.py:37) |
| GET | `/api/v1/notifications/unread-count` | `get_unread_count` (24) | NotificationService.get_unread_count (app/common/services/notification_service.py:194) |
| PATCH | `/api/v1/notifications/{notification_id:int}/read` | `mark_notification_read` (33) | NotificationService.mark_notification_read (app/common/services/notification_service.py:214) |
| POST | `/api/v1/notifications/{notification_id:int}/read` | `mark_notification_read` (33) | NotificationService.mark_notification_read (app/common/services/notification_service.py:214) |
| PATCH | `/api/v1/notifications/read-all` | `mark_all_notifications_read` (43) | NotificationService.mark_all_notifications_read (app/common/services/notification_service.py:221) |
| POST | `/api/v1/notifications/read-all` | `mark_all_notifications_read` (43) | NotificationService.mark_all_notifications_read (app/common/services/notification_service.py:221) |
| DELETE | `/api/v1/notifications/{notification_id:int}` | `delete_notification` (51) | NotificationService.delete_notification (app/common/services/notification_service.py:230) |

## app/post/routes.py

| Method | Path | Handler | Service method |
|---|---|---|---|
| POST | `/api/v1/posts` | `create_post` (50) | PostService.assert_can_create (app/common/services/post_service.py:152)<br>PostService.parse_scheduled_at (app/common/services/post_service.py:171)<br>PostService.create_post (app/common/services/post_service.py:300)<br>PostService.parse_poll_options (app/common/services/post_service.py:159)<br>PostService.music_from_form (app/common/services/post_service.py:188) |
| GET | `/api/v1/posts` | `get_feed` (112) | PostService.get_feed (app/common/services/post_service.py:367) |
| GET | `/api/v1/posts/scheduled` | `list_scheduled_posts` (122) | PostService.list_scheduled_posts (app/common/services/post_service.py:529) |
| GET | `/api/v1/posts/saved` | `list_saved_posts` (144) | PostService.list_saved_posts (app/common/services/post_service.py:482) |
| GET | `/api/v1/posts/archived` | `list_archived_posts` (155) | PostService.list_archived_posts (app/common/services/post_service.py:507) |
| GET | `/api/v1/posts/{post_id:int}` | `get_one_post` (166) | PostService.get_one_post (app/common/services/post_service.py:460) |
| PATCH | `/api/v1/posts/{post_id:int}/schedule` | `reschedule_post` (175) | PostService.reschedule_post (app/common/services/post_service.py:741) |
| POST | `/api/v1/posts/{post_id:int}/publish` | `publish_post_now` (185) | PostService.publish_post_now (app/common/services/post_service.py:757) |
| PATCH | `/api/v1/posts/{post_id:int}` | `edit_post` (192) | PostService.edit_post (app/common/services/post_service.py:784) |
| POST | `/api/v1/posts/{post_id:int}/archive` | `archive_post` (203) | PostService.archive_post (app/common/services/post_service.py:869) |
| POST | `/api/v1/posts/{post_id:int}/restore` | `restore_post` (210) | PostService.restore_post (app/common/services/post_service.py:873) |
| POST | `/api/v1/posts/{post_id:int}/pin` | `pin_post` (217) | PostService.pin_post (app/common/services/post_service.py:877) |
| DELETE | `/api/v1/posts/{post_id:int}/pin` | `unpin_post` (224) | PostService.unpin_post (app/common/services/post_service.py:881) |
| DELETE | `/api/v1/posts/{post_id:int}` | `delete_post` (231) | PostService.delete_post (app/common/services/post_service.py:885) |
| POST | `/api/v1/posts/{post_id:int}/vote` | `vote_in_poll` (240) | PostService.vote_in_poll (app/common/services/post_service.py:904) |
| POST | `/api/v1/posts/{post_id:int}/like` | `like_post` (248) | PostEngagementService.like_post (app/common/services/post_engagement_service.py:294) |
| DELETE | `/api/v1/posts/{post_id:int}/like` | `unlike_post` (255) | PostEngagementService.unlike_post (app/common/services/post_engagement_service.py:310) |
| GET | `/api/v1/posts/{post_id:int}/likes` | `list_post_likers` (262) | PostEngagementService.list_post_likers (app/common/services/post_engagement_service.py:329) |
| POST | `/api/v1/posts/{post_id:int}/save` | `save_post` (273) | PostEngagementService.save_post (app/common/services/post_engagement_service.py:365) |
| DELETE | `/api/v1/posts/{post_id:int}/save` | `unsave_post` (280) | PostEngagementService.unsave_post (app/common/services/post_engagement_service.py:378) |
| POST | `/api/v1/posts/{post_id:int}/share` | `share_post` (287) | PostEngagementService.share_post (app/common/services/post_engagement_service.py:392) |
| POST | `/api/v1/posts/{post_id:int}/view` | `view_post` (298) | PostEngagementService.view_post (app/common/services/post_engagement_service.py:441) |
| POST | `/api/v1/posts/{post_id:int}/report` | `report_post` (306) | PostEngagementService.report_post (app/common/services/post_engagement_service.py:455) |
| GET | `/api/v1/posts/{post_id:int}/insights` | `get_post_insights` (314) | PostEngagementService.get_post_insights (app/common/services/post_engagement_service.py:485) |
| GET | `/api/v1/posts/{post_id:int}/comments` | `list_post_comments` (324) | PostEngagementService.list_post_comments (app/common/services/post_engagement_service.py:593) |
| POST | `/api/v1/posts/{post_id:int}/comments` | `add_post_comment` (337) | PostEngagementService.add_post_comment (app/common/services/post_engagement_service.py:650) |
| GET | `/api/v1/posts/{post_id:int}/comments/{comment_id:int}/replies` | `list_comment_replies` (347) | PostEngagementService.list_comment_replies (app/common/services/post_engagement_service.py:619) |
| DELETE | `/api/v1/posts/{post_id:int}/comments/{comment_id:int}` | `delete_post_comment` (359) | PostEngagementService.delete_post_comment (app/common/services/post_engagement_service.py:706) |
| POST | `/api/v1/posts/{post_id:int}/comments/{comment_id:int}/like` | `like_post_comment` (369) | PostEngagementService.like_post_comment (app/common/services/post_engagement_service.py:736)<br>PostEngagementService.unlike_post_comment (app/common/services/post_engagement_service.py:758) |
| DELETE | `/api/v1/posts/{post_id:int}/comments/{comment_id:int}/like` | `unlike_post_comment` (383) | PostEngagementService.unlike_post_comment (app/common/services/post_engagement_service.py:758) |
| POST | `/api/v1/posts/{post_id:int}/comments/{comment_id:int}/unlike` | `unlike_post_comment` (383) | PostEngagementService.unlike_post_comment (app/common/services/post_engagement_service.py:758) |
| GET | `/api/v1/posts/{post_id:int}/media` | `get_post_media` (413) | PostService.media_info (app/common/services/post_service.py:934)<br>PostService.media_bytes (app/common/services/post_service.py:957) |

## app/profile/routes.py

| Method | Path | Handler | Service method |
|---|---|---|---|
| GET | `/api/v1/users/by-username/{username}` | `get_public_profile` (13) | ProfileService.get_public_profile (app/common/services/profile_service.py:85) |
| GET | `/api/v1/users/by-username/{username}/posts` | `get_user_public_posts` (22) | PostService.get_user_public_posts (app/common/services/post_service.py:404) |

## app/story/routes.py

| Method | Path | Handler | Service method |
|---|---|---|---|
| GET | `/api/v1/stories/feed` | `get_stories_feed` (61) | StoryFeedService.get_stories_feed (app/common/services/story/story_feed_service.py:85) |
| GET | `/api/v1/stories` | `list_active_stories` (71) | StoryFeedService.list_active_stories (app/common/services/story/story_feed_service.py:158) |
| GET | `/api/v1/stories/my` | `get_my_stories` (79) | StoryFeedService.get_my_stories (app/common/services/story/story_feed_service.py:292) |
| GET | `/api/v1/stories/stats/me` | `get_my_story_stats` (87) | StoryAnalyticsService.get_my_story_stats (app/common/services/story/story_analytics_service.py:210) |
| GET | `/api/v1/stories/my-story-analytics` | `get_my_story_analytics` (95) | StoryAnalyticsService.get_my_story_analytics (app/common/services/story/story_analytics_service.py:254) |
| GET | `/api/v1/stories/owner-feed` | `get_owner_story_feed` (103) | StoryFeedService.get_owner_story_feed (app/common/services/story/story_feed_service.py:42) |
| GET | `/api/v1/stories/archived` | `get_archived_stories` (111) | StoryFeedService.get_archived_stories (app/common/services/story/story_feed_service.py:442) |
| GET | `/api/v1/stories/saved` | `get_saved_stories` (119) | StoryFeedService.get_saved_stories (app/common/services/story/story_feed_service.py:421) |
| GET | `/api/v1/stories/music/trending` | `get_trending_music` (127) | MusicService.get_trending_music (app/common/services/music_service.py:80) |
| GET | `/api/v1/stories/music/search` | `search_music` (135) | MusicService.search_music (app/common/services/music_service.py:167) |
| GET | `/api/v1/stories/user/{user_id}` | `get_user_stories` (144) | StoryFeedService.get_user_stories (app/common/services/story/story_feed_service.py:314) |
| GET | `/api/v1/stories/{story_id:int}` | `get_single_story` (154) | StoryFeedService.get_single_story (app/common/services/story/story_feed_service.py:381) |
| POST | `/api/v1/stories/upload` | `upload_single_story` (164) | StoryCreationService.upload_single_story (app/common/services/story/story_creation_service.py:150) |
| POST | `/api/v1/stories/upload-multiple` | `upload_multiple_stories` (177) | StoryCreationService.upload_multiple_stories (app/common/services/story/story_creation_service.py:210) |
| POST | `/api/v1/stories` | `create_story` (190) | StoryCreationService.create_story (app/common/services/story/story_creation_service.py:41) |
| POST | `/api/v1/stories/text` | `create_text_story` (199) | StoryCreationService.create_text_story (app/common/services/story/story_creation_service.py:107) |
| PATCH | `/api/v1/stories/{story_id:int}` | `edit_story` (208) | StoryCreationService.edit_story (app/common/services/story/story_creation_service.py:296) |
| DELETE | `/api/v1/stories/{story_id:int}` | `delete_story` (218) | StoryCreationService.delete_story (app/common/services/story/story_creation_service.py:313) |
| POST | `/api/v1/stories/{story_id:int}/view` | `record_story_view` (228) | StoryEngagementService.record_story_view (app/common/services/story/story_engagement_service.py:39) |
| POST | `/api/v1/stories/{story_id:int}/like` | `like_story` (237) | StoryEngagementService.like_story (app/common/services/story/story_engagement_service.py:87) |
| DELETE | `/api/v1/stories/{story_id:int}/like` | `unlike_story` (246) | StoryEngagementService.unlike_story (app/common/services/story/story_engagement_service.py:146) |
| POST | `/api/v1/stories/{story_id:int}/react` | `react_to_story` (255) | StoryEngagementService.react_to_story (app/common/services/story/story_engagement_service.py:422) |
| POST | `/api/v1/stories/{story_id:int}/reply` | `reply_to_story` (265) | StoryEngagementService.reply_to_story (app/common/services/story/story_engagement_service.py:247) |
| GET | `/api/v1/stories/{story_id:int}/comments` | `get_story_comments` (275) | StoryEngagementService.get_story_comments (app/common/services/story/story_engagement_service.py:307) |
| POST | `/api/v1/stories/{story_id:int}/pause` | `pause_story` (284) | StoryEngagementService.pause_story (app/common/services/story/story_engagement_service.py:189) |
| GET | `/api/v1/stories/{story_id:int}/activity` | `get_story_activity` (297) | StoryAnalyticsService.get_story_activity (app/common/services/story/story_analytics_service.py:35) |
| GET | `/api/v1/stories/{story_id:int}/viewers` | `get_story_viewers` (306) | StoryAnalyticsService.get_story_viewers (app/common/services/story/story_analytics_service.py:116) |
| GET | `/api/v1/stories/{story_id:int}/likers` | `get_story_likers` (317) | StoryAnalyticsService.get_story_likers (app/common/services/story/story_analytics_service.py:163) |
| POST | `/api/v1/stories/{story_id:int}/share` | `share_story` (328) | StoryEngagementService.share_story (app/common/services/story/story_engagement_service.py:331) |
| POST | `/api/v1/stories/{story_id:int}/reshare` | `reshare_story` (340) | StoryCreationService.reshare_story (app/common/services/story/story_creation_service.py:346) |
| GET | `/api/v1/stories/mentions/search` | `search_mention_users` (350) | StoryMentionService.search_mention_users (app/common/services/story/story_mention_service.py:31) |
| POST | `/api/v1/stories/{story_id:int}/mentions` | `add_mention_to_story` (361) | StoryMentionService.add_mention_to_story (app/common/services/story/story_mention_service.py:93) |
| POST | `/api/v1/stories/{story_id:int}/save` | `save_story` (373) | StoryEngagementService.save_story (app/common/services/story/story_engagement_service.py:377) |
| DELETE | `/api/v1/stories/{story_id:int}/save` | `unsave_story` (382) | StoryEngagementService.unsave_story (app/common/services/story/story_engagement_service.py:404) |
| POST | `/api/v1/stories/{story_id:int}/report` | `report_story` (391) | StoryEngagementService.report_story (app/common/services/story/story_engagement_service.py:484) |
| POST | `/api/v1/stories/mute/{user_id:int}` | `mute_creator` (402) | StoryRelationshipService.mute_creator (app/common/services/story/story_relationship_service.py:26) |
| POST | `/api/v1/stories/users/{user_id:int}/mute` | `mute_creator` (402) | StoryRelationshipService.mute_creator (app/common/services/story/story_relationship_service.py:26) |
| DELETE | `/api/v1/stories/mute/{user_id:int}` | `unmute_creator` (412) | StoryRelationshipService.unmute_creator (app/common/services/story/story_relationship_service.py:52) |
| DELETE | `/api/v1/stories/users/{user_id:int}/mute` | `unmute_creator` (412) | StoryRelationshipService.unmute_creator (app/common/services/story/story_relationship_service.py:52) |
| POST | `/api/v1/stories/follow/{user_id:int}` | `follow_user` (421) | StoryRelationshipService.follow_user (app/common/services/story/story_relationship_service.py:70) |
| DELETE | `/api/v1/stories/follow/{user_id:int}` | `unfollow_user` (430) | StoryRelationshipService.unfollow_user (app/common/services/story/story_relationship_service.py:108) |
| GET | `/api/v1/stories/suggestions` | `get_suggestions` (439) | StoryRelationshipService.get_suggestions (app/common/services/story/story_relationship_service.py:142) |

## app/story/settings_routes.py

| Method | Path | Handler | Service method |
|---|---|---|---|
| GET | `/api/v1/stories/settings/muted` | `list_muted_creators` (15) | StorySettingsService.list_muted_creators (app/common/services/story/story_settings_service.py:16) |
| DELETE | `/api/v1/stories/settings/muted/{user_id:int}` | `remove_muted_creator` (23) | StorySettingsService.remove_muted_creator (app/common/services/story/story_settings_service.py:28) |
| GET | `/api/v1/stories/settings/close-friends` | `list_close_friends` (33) | StorySettingsService.list_close_friends (app/common/services/story/story_settings_service.py:44) |
| POST | `/api/v1/stories/settings/close-friends/{friend_id:int}` | `add_close_friend` (41) | StorySettingsService.add_close_friend (app/common/services/story/story_settings_service.py:56) |
| DELETE | `/api/v1/stories/settings/close-friends/{friend_id:int}` | `remove_close_friend` (50) | StorySettingsService.remove_close_friend (app/common/services/story/story_settings_service.py:76) |
| GET | `/api/v1/stories/settings/followers/{user_id:int}` | `list_followers` (60) | StorySettingsService.list_followers (app/common/services/story/story_settings_service.py:92) |
| GET | `/api/v1/stories/settings/following/{user_id:int}` | `list_following` (70) | StorySettingsService.list_following (app/common/services/story/story_settings_service.py:108) |
