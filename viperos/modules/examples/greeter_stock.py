"""
Example stock module: a simple startup greeter.

This is the kind of thing that belongs under modman, not core/: it's not
needed for the OS to function, and a user should be free to replace it
with their own version via `modman replace greeter <their_script>`.
"""


def run():
    print("Welcome to ViperOS.")
