"""Flet presentation layer for the Library Management System.

Architecture per the approved Presentation Architecture Review (PAR):
- Screens live under :mod:`app.presentation.screens` and act as their own
  controllers (Volume 3, Chapter 18.1 event-handler pattern).
- Screens receive their services via constructor injection; the composition
  root in :mod:`app.main` is the only place that instantiates services.
- The layer may import only ``app.services``, ``app.core`` and ``app.utils``.
  It never imports repositories, models, the database engine or SQLAlchemy.
"""