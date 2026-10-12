"""Select a user's view of the configured Plex server without changing global state."""

from plexapi.server import PlexServer


class ProfileAccessError(ValueError):
    pass


def server_for_user(plex, username=None, user_id=None):
    if username is None and user_id is None:
        return plex
    if user_id is not None and user_id <= 0:
        raise ProfileAccessError("user_id must be a positive Plex user ID")
    if username is not None and not username.strip():
        raise ProfileAccessError("username must not be empty")
    try:
        account = plex.myPlexAccount()
        def matches(user):
            if user_id is not None:
                return str(user.id) == str(user_id)
            names = [getattr(user, field, None) for field in ("username", "title")]
            return any(name and name.casefold() == username.strip().casefold() for name in names)

        if user_id is not None and matches(account):
            return plex
        candidates = [user for user in account.users() if matches(user)]
        if user_id is None and matches(account):
            candidates.append(account)
        if not candidates:
            raise ProfileAccessError("User not found. Use user_list_all_users to find their user_id.")
        if len(candidates) != 1:
            raise ProfileAccessError("Multiple users match that name. Supply user_id instead.")
        target = candidates[0]
        if target is account:
            return plex
        token = target.get_token(plex.machineIdentifier)
        if not token:
            raise ProfileAccessError("Plex did not provide server access for this user. The configured account must administer the server.")
        return PlexServer(plex._baseurl, token=token, timeout=15)
    except ProfileAccessError:
        raise
    except Exception:
        raise ProfileAccessError("Unable to access this user's Plex server profile") from None
