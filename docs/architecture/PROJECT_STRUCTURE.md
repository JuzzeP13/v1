# Project Structure (Feature-Oriented)

The project is split by features to keep code and assets easy to navigate:

- `modules/main/python/`
  - Core app setup, analysis pipeline, main routes, API/download routes.
- `modules/common/python/`
  - Shared config and i18n modules.
- `modules/auth/python/`
  - Authentication, users model, and security logic.
- `modules/profile/python/`
  - Online user activity tracking and shared admin/profile activity state.
- `modules/admin/python/`
  - Admin panel routes and admin API endpoints.
- `modules/chat/python/`
  - Socket.IO handlers, social/product/youtube processing, excel exports, social search engine.
- `modules/integration/python/`
  - Main site API integration and synchronization.
- `modules/search/python/`
  - Search cache and search optimization utilities.
- `modules/system/python/`
  - System scripts (`init_app`, `backup`, `celery_worker`, CLI helper).
- `modules/migrations/python/`
  - Database migration scripts.

Frontend is also split by features:

- `templates/main/` + `static/main/`
- `templates/profile/` + `static/profile/`
- `templates/admin/` + `static/admin/`
- `static/chat/` (chat/runtime JS split from main dashboard script)

Entrypoints are module-based:

- `python -m modules.main.python.server` for development server.
- `python -m modules.system.python.run` for production launcher.
- `python -m modules.system.python.init_app` for initialization.

Legacy templates are kept as small include wrappers for backward compatibility:

- `templates/index.html` -> `templates/main/index.html`
- `templates/admin.html` -> `templates/admin/admin.html`
- `templates/admin_login.html` -> `templates/admin/admin_login.html`
- `templates/subscription.html` -> `templates/main/subscription.html`
- `templates/auth/profile.html` -> `templates/profile/profile.html`

