# Changelog

All notable changes to this project will be documented in this file.

## [1.1.3] - 2026-02-08

### Added
- **Advanced Library Filtering**: `library_get_contents` now supports filtering by `watched`, `genre`, `year`, `content_rating`, `director`, `actor`, `writer`, `resolution`, `network`, and `studio`

### Fixed
- **Playback History Performance**: `sessions_get_media_playback_history` now uses batch fetching for account and device lookups, eliminating N+1 network calls that caused severe delays on shows with large history counts
