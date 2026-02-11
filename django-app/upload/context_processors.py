"""
Context processor to expose the user's admin status to all templates.
"""


def admin_status(request):
    """Add `is_admin` boolean to template context."""
    if request.user.is_authenticated:
        return {
            'is_admin': (
                request.user.is_superuser
                or request.user.groups.filter(name='admins').exists()
            )
        }
    return {'is_admin': False}
