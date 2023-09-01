# WebTickets

.env file is needed for global variables to work correctly.

v1.7:

# -- Put Redis Port and Host in .env.
# -- filter out tickets in '8 Time' for client portal.
# -- Renamed variables to keep updated to coding standards.
# -- Displays lastest 10 entries of logged in user.
# -- Adds testing mode.
# -- Displays last 10 time entries on employee portal
# -- excludes tickets with "-2DEL-" in its subject
# -- Removes location and attendess box from time entry.
# -- Adds text field padding on time entry.
# -- Autofills datetime to current time in time entry form.
# -- Includes new "index" route for users homepage.

# Speical Cases:
# Client Portal:
# -- filter out tickets in '8 Time' and "9 Review" for client portal
# -- filter out tickets with a '#' after CLIENTID and TICKETNUMBER
# -- filter out tickets with "-2DEL-" in subject line
# Employee Portal:
# -- filter out tickets in "9 Review for employee portal"
# -- includes placeholder tickets.
