# Parked layout sources

Layout sources awaiting a selectable profile belong outside `layouts/internal/src`.
The layout compiler and the Android
`generateInternalLayoutRegistry` task both require the source set to exactly equal
the set of layouts bound by selectable profiles, so an unbound source fails the
internal build closed.

Promoting a profile moves its source into `src/` and its notice, when present,
into `notices/` as part of the finalizer and relock transaction.

No layout sources are parked here currently.
