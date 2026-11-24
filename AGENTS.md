# Working on the toolkit

Preserve Python 3.9 compatibility and the standard-library runtime. Make changes from the repository root. Run `python -m unittest discover -s tests -t .`, `python -m mktgkit demo`, and verify a wheel install outside the checkout when packaging changes. All example business data is fictional. Keep secrets, provider accounts and private customer records out of fixtures.

Check the normal CLI workflow when changing approval, permission, freshness or handoff behavior. Regression tests must exercise a refused case as well as a successful one. Workspace operator instructions live under the template; this file is for contributors to the software.
