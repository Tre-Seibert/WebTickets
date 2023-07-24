# v1.7
# -- Put Redis Port and Host in .env
# -- filter out tickets in '9 Time' for client portal
# -- Renamed variables to keep updated to coding standards

# high and urgent red

###############
# IMPORTS
###############


# INTERNAL:
import os # Gets the env variables from .env file
import secrets # For flask managing session tokens

# EXTERNAL:
from dotenv import load_dotenv # For loading environment variables
from msal import ConfidentialClientApplication # For interactive authentication
from flask import Flask, render_template, request, session, redirect, send_from_directory # For creating web app
from redis import Redis # For access token caching
from flask_session import Session # For session handling
from exchangelib import DELEGATE, Account, Configuration, ExtendedProperty, Task, CalendarItem, OAuth2AuthorizationCodeCredentials, OAUTH2, OAuth2LegacyCredentials # For exporting tickets
from exchangelib.items import SEND_TO_ALL_AND_SAVE_COPY # For sending time entrys 
from pytz import timezone # For converting timezones
from datetime import datetime, timedelta # For converting times


###############
# GLOBALS
###############

# Load env variables
load_dotenv()

m_sClientID = os.getenv("CLIENT_ID")
m_sClientSecret = os.getenv("CLIENT_SECRET")
m_sRedirectURI = os.getenv("REDIRECT_URI")
m_sAuthority = os.getenv("AUTHORITY")
m_sTenant = os.getenv("TENANT")
m_sEmail = os.getenv("EMAIL")
m_sPassword = os.getenv("PASSWORD")
m_sScope = ["EWS.AccessAsUser.All"]
m_sHost = os.getenv("REDIS_HOST")
m_sPort = os.getenv("REDIS_PORT")

# Create instance of ClientApp
webTicketsApp = ConfidentialClientApplication(client_id=m_sClientID, client_credential=m_sClientSecret, authority=m_sAuthority)


########################
# Flask Configuration
########################

# Create a Flask web application instance.
app = Flask(__name__)

# Generate a secret key
secret_key = secrets.token_hex(16)

# Create session secret key
app.secret_key = secret_key

# Sets the max session length to 30 minutes
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

# Sets the session type to a redis type
app.config['SESSION_TYPE'] = 'redis'

# Use this line in testing.
# r = Redis(host='localhost', port=6379, db=0)

# Use this line in production instead.
r = Redis(host=m_sHost, port=m_sPort, db=0)

# Points to redis server session.
app.config['SESSION_REDIS'] = r

# Initialize Session
Session(app)

# Set the template folder for Flask to the absolute path of the current directory.
# Root is the directory of the account 'TBAdmin' user account, "my_flask_app"
template_folder = os.path.abspath(os.path.dirname(__file__))
app.template_folder = template_folder


#######################
# Extended Properties 
#######################

# Define the extended properties
class DateCreated(ExtendedProperty):
    distinguished_property_set_id = 'PublicStrings'
    property_name = '.DateCreated'
    property_type = 'SystemTime'

class Client(ExtendedProperty):
    distinguished_property_set_id = 'PublicStrings'
    property_name = '.Client'
    property_type = 'String'

class Assignee(ExtendedProperty):
    distinguished_property_set_id = 'PublicStrings'
    property_name = '.Assignee'
    property_type = 'String'

class HrsActualTotal(ExtendedProperty):
    distinguished_property_set_id = 'PublicStrings'
    property_name = '.HrsActualTotal'
    property_type = 'Double'

class DateLastActivity(ExtendedProperty):
    distinguished_property_set_id = 'PublicStrings'
    property_name = '.DateLastActivity'
    property_type = 'SystemTime'

# Register extended properties
Task.register('dateCreated_property', DateCreated)
Task.register('client_property', Client)
Task.register('assignee_property', Assignee)
Task.register('hrsActualTotal_property', HrsActualTotal)
Task.register('datelastactivity_property', DateLastActivity)


##################
#  / Root Path
##################
@app.route('/')
def index():
    # Checks for token in redis cache
    if "access_token" in session:
        # Define Exchangelib creds.
        creds = OAuth2AuthorizationCodeCredentials(access_token=session["access_token"])
        print("Token: " + str(session["access_token"]))

        # Define Exchangelib config.
        conf = Configuration(server="outlook.office365.com", auth_type=OAUTH2, credentials=creds)

        # Define the Exchangelib account, passing creds w/ access token
        account = Account(
            primary_smtp_address=session["email"],
            access_type=DELEGATE,
            config=conf,
            autodiscover=False,
        )

        # Gets users email, name and assigneeID
        email = str(session["email"])
        name = str(session["name"])
        assignee = email[:2]
        
        return fetch_tasks_assignee(assignee)
    else:
        # If access token is not in redis cache:
        # 1. Generate auth url
        # 2. Redirect to 365 login.
        auth_url = webTicketsApp.get_authorization_request_url(scopes=m_sScope, redirect_uri=m_sRedirectURI)
        print(auth_url) # debug
        return redirect(auth_url)
    

#################################
# Callback Route
# Redirect after authentication
#################################
@app.route("/callback")
def callback():

    # Get auth code from response
    code = request.args.get("code")
    result = webTicketsApp.acquire_token_by_authorization_code(
        code,
        scopes=m_sScope,
        redirect_uri=m_sRedirectURI
    )

    # Store access token in cache
    session["access_token"] = result
    print(str(result)) # debug

    # Store email in cache
    session["email"] = result["id_token_claims"]["preferred_username"]

    # Store name in cache
    session["name"] = result["id_token_claims"]["name"]
    print("Session: " + session["name"])

    # Redirect to root(/) route
    return redirect("/")


#########################
# Favicon Route
########################
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico',mimetype='image/vnd.microsoft.icon')


#########################
# Create Meeting Route
#########################
@app.route('/create-meeting', methods=['POST'])
def create_meeting_request():
    if request.method == 'POST':
        # Checks for token in redis cache
        if "access_token" in session:

            # Retrieve user input from html
            subject = request.form.get('subject')
            start_time = request.form.get('start_time')
            end_time = request.form.get('end_time')
            location = request.form.get('location')
            attendees = [email.strip() for email in request.form.get('attendees').split(',')]
            body = request.form.get('body')

            # Define Exchangelib creds.
            creds = OAuth2AuthorizationCodeCredentials(access_token=session["access_token"])
            print("Creds var: " + str(creds))

            # Define Exchangelib config.
            conf = Configuration(server="outlook.office365.com", auth_type=OAUTH2, credentials=creds)

            # Define the Exchangelib account, passing creds w/ access token
            account = Account(
                primary_smtp_address=session["email"],
                access_type=DELEGATE,
                config=conf,
                autodiscover=False,
            )

            # Define the time zone
            time_zone = timezone('US/Eastern')

            # Convert start_time and end_time strings to datetime objects in the specified time zone
            start_datetime = time_zone.localize(datetime.strptime(start_time, '%Y-%m-%dT%H:%M'))
            end_datetime = time_zone.localize(datetime.strptime(end_time, '%Y-%m-%dT%H:%M'))

            # Define calendar item
            item = CalendarItem(
                account=account,
                folder=account.calendar,
                start=start_datetime,
                end=end_datetime,
                subject=subject,
                location=location,
                body=body,
                required_attendees=attendees
            )
            
            # Send time entry
            item.save(send_meeting_invitations=SEND_TO_ALL_AND_SAVE_COPY)

            # Return success message
            return "Time entry submitted successfully."
        else:
            # Return error page.
            render_template("error.html")


###############################
# Fetch Tasks /clientID Route
###############################
@app.route('/fetch-tasks/<string:clientID>')
def fetch_tasks(clientID):
    # Make sure clientID is uppercase (all of our client ID's on 365 are uppercase)
    clientID = clientID.upper()
    # Checks for token in redis cache
    if "access_token" in session:

        # Define Exchangelib creds.
        creds = OAuth2AuthorizationCodeCredentials(access_token=session["access_token"])
        print("Creds var: " + str(creds))

        # Define Exchangelib config.
        conf = Configuration(server="outlook.office365.com", auth_type=OAUTH2, credentials=creds)
        
        # Define the Exchangelib account, passing creds w/ access token
        account = Account(
            primary_smtp_address=session["email"],
            access_type=DELEGATE,
            config=conf,
            autodiscover=False,
        )

        # Traverse to our public folders root. "All Public Folders"
        fPublic = account.public_folders_root
        
        # Define folders to search for
        fTB = 'TECHBLDRS INC'
        fSubfolder = 'TB Tickets'

        # Traverse to 'TB Tickets' folder
        fParent = fPublic / fTB
        cTasks = fParent / fSubfolder # This should be a folder

        # Sort the tasks by passed clinetID 
        cSortedTickets = cTasks.filter(client_property__exact=clientID).order_by('client_property', '-dateCreated_property')
        
        # Sort the tasks by clinetID none for place holder tickets
        cSortedTicketsNone = cTasks.filter(assignee_property__exact="").order_by('client_property', '-dateCreated_property')

        # Define list to store tickets with assignee=""
        listTicketsNone = []

        for task in reversed(list(cSortedTicketsNone)):
            if task.categories == ["Place Holder"]:
                ticketsNone_data = {
                    'Subject': task.subject,
                    'Category': task.categories,
                    'Date Created': task.dateCreated_property,
                    'Hours (Actual)': task.hrsActualTotal_property,
                    'Last Activity': task.datelastactivity_property
                }
                listTicketsNone.append(ticketsNone_data)
        
        # Define list to store tickets
        # This list contains the complete ticket with formatted dates
        listTickets = []

        # Traverse through the cSortedTickets (reversed so that last activity is at the top)
        for task in reversed(list(cSortedTickets)):
            print(type(task.subject))
            # Filter out the tickets in 'Review' category
            if task.categories != ["9 REVIEW"]:
                # Parse the properties to the dictionary
                # This dict contains the ticket without a formatted date
                tickets_data = {
                    'Subject': task.subject,
                    'Category': task.categories,
                    'Date Created': task.dateCreated_property,
                    'Hours (Actual)': task.hrsActualTotal_property,
                    'Last Activity': task.datelastactivity_property
                }
                # Add to listTickets dictionary
                listTickets.append(tickets_data)
        
        # Convert the "Last Activity" timestamp to Eastern Standard Time (EST)
        # Convert to 12-hour time
        eastern_tz = timezone('America/New_York')
        for tickets_data in listTickets:
            tickets_data['Date Created'] = tickets_data['Date Created'].strftime('%Y-%m-%d %I:%M %p')
            last_activity_utc = tickets_data['Last Activity']
            last_activity_est = last_activity_utc.astimezone(eastern_tz)
            tickets_data['Last Activity'] = last_activity_est.strftime('%Y-%m-%d %I:%M %p')
        
        for ticketsNone_data in listTicketsNone:
            ticketsNone_data['Date Created'] = ticketsNone_data['Date Created'].strftime('%Y-%m-%d %I:%M %p')
            last_activity_utc = ticketsNone_data['Last Activity']
            last_activity_est = last_activity_utc.astimezone(eastern_tz)
            ticketsNone_data['Last Activity'] = last_activity_est.strftime('%Y-%m-%d %I:%M %p')

        merged_dict = listTickets + listTicketsNone

        # Pass the clientID and listTickets list to html render
        return render_template('task_list.html', clientID=clientID, tasks=merged_dict)
    else:
        # Return error page.
        return render_template("error.html")



###############################
# Fetch Tasks /assigneeID Route
###############################
@app.route('/fetch-tasks-by-assignee/<string:assigneeID>')
def fetch_tasks_assignee(assigneeID):
    # Make sure assigneeID is lowercase (all of our assignee ID's on 365 are lowercase)
    assigneeID = assigneeID.lower()
    # Checks for token in redis cache
    if "access_token" in session:
        # Define Exchangelib creds.
        creds = OAuth2AuthorizationCodeCredentials(access_token=session["access_token"])
        print("Creds var: " + str(creds))

        # Define Exchangelib config.
        conf = Configuration(server="outlook.office365.com", auth_type=OAUTH2, credentials=creds)

        # Define the Exchangelib account, passing creds w/ access token
        account = Account(
            primary_smtp_address=session["email"],
            access_type=DELEGATE,
            config=conf,
            autodiscover=False,
        )
        
        # Traverse to our public folders root.
        fPublic = account.public_folders_root

        # Define folders to search for
        fTB = 'TECHBLDRS INC'
        fSubfolder = 'TB Tickets'

        # Traverse to 'TB Tickets' folder
        fParent = fPublic / fTB
        cTasks = fParent / fSubfolder


        # Sort the tasks by passed assigneeID 
        cSortedTickets = cTasks.filter(assignee_property__exact=assigneeID).order_by('client_property', '-dateCreated_property')

        # Sort the tasks by assigneeID as none
        cSortedTicketsNone = cTasks.filter(assignee_property__exact="").order_by('client_property', '-dateCreated_property')


        # Define list to store tickets with assignee=""
        # This list contains the complete ticket
        listTicketsNone = []

        for task in reversed(list(cSortedTicketsNone)):
            # Filter for tickets in 'Place Holder' category
            if task.categories == ["Place Holder"]:
                # Parse the properties to the dictionary
                # This dict contains the tickets (in 'Place Holder' category) without a formatted date
                ticketsNone_data = {
                    'Subject': task.subject,
                    'Category': task.categories,
                    'Date Created': task.dateCreated_property,
                    'Hours (Actual)': task.hrsActualTotal_property,
                    'Last Activity': task.datelastactivity_property
                }
                # Add to listTicketsNone dictionary
                listTicketsNone.append(ticketsNone_data)


        # Define list to store tickets
        # This list contains the complete ticket
        listTickets = []

        # Traverse through the cSortedTickets (reversed so that last activity is at the top)
        for task in reversed(list(cSortedTickets)):
            print(type(task.subject))
            # Filter out the tickets in 'Review' category
            if task.categories != ["9 REVIEW"]:
                    # Parse the properties to the dictionary
                    # This dict contains the ticket without a formatted date
                    tickets_data = {
                        'Subject': task.subject,
                        'Category': task.categories,
                        'Date Created': task.dateCreated_property,
                        'Hours (Actual)': task.hrsActualTotal_property,
                        'Last Activity': task.datelastactivity_property
                    }
                    # Add to listTickets dictionary
                    listTickets.append(tickets_data)
        
        # Convert the "Last Activity" timestamp to Eastern Standard Time (EST)
        # Convert to 12-hour time
        eastern_tz = timezone('America/New_York')
        for tickets_data in listTickets:
            tickets_data['Date Created'] = tickets_data['Date Created'].strftime('%Y-%m-%d %I:%M %p')
            last_activity_utc = tickets_data['Last Activity']
            last_activity_est = last_activity_utc.astimezone(eastern_tz)
            tickets_data['Last Activity'] = last_activity_est.strftime('%Y-%m-%d %I:%M %p')

        for ticketsNone_data in listTicketsNone:
            ticketsNone_data['Date Created'] = ticketsNone_data['Date Created'].strftime('%Y-%m-%d %I:%M %p')
            last_activity_utc = ticketsNone_data['Last Activity']
            last_activity_est = last_activity_utc.astimezone(eastern_tz)
            ticketsNone_data['Last Activity'] = last_activity_est.strftime('%Y-%m-%d %I:%M %p')

        merged_dict = listTickets + listTicketsNone
        assigneeID = assigneeID.upper()
        # Pass the assigneeID and listTickets list to html render
        return render_template('task_list_employee.html', assigneeID=assigneeID, tasks=merged_dict)
    else:
        # Return error page.
        return render_template("error.html")



#########################################
# Client Portal Code Below:
# - note: The new features in v1.6 are
# not implemented to client portal
#########################################


###############################
# fetch-tasks-client/clientID Route
###############################
@app.route('/fetch-tasks-client/<string:clientID>')
def fetch_tasks_client(clientID):

    # Make sure clientID is uppercase (all of our client ID's on 365 are uppercase)
    clientID = clientID.upper()
    # Define Exchangelib creds. 
    credentials = OAuth2LegacyCredentials(
        client_id=m_sClientID,
        client_secret=m_sClientSecret,
        tenant_id=m_sTenant,
        username=m_sEmail,
        password=m_sPassword
    )
    config = Configuration(server='outlook.office365.com', credentials=credentials)
    account = Account(m_sEmail, config=config, access_type=DELEGATE)
    
    # Traverse to our public folders root. "All Public Folders"
    fPublic = account.public_folders_root
    
    # Define folders to search for
    fTB = 'TECHBLDRS INC'
    fSubfolder = 'TB Tickets'

    # Traverse to 'TB Tickets' folder
    fParent = fPublic / fTB
    cTasks = fParent / fSubfolder # This should be a folder

    # Sort the tasks by passed clinetID 
    cSortedTickets = cTasks.filter(client_property__exact=clientID).order_by('-dateCreated_property')
    
    # Define list to store tickets
    # This list contains the complete ticket with formatted dates.
    listTickets = []

    # Traverse through the cSortedTickets (reversed so that last activity is at the top)
    for task in reversed(list(cSortedTickets)):
        print(type(task.subject))
        # Filter out the tickets in 'Review' category
        if task.categories != ["9 REVIEW"] and task.categories != ["8 Time"]:
            # Filter out tickets with "#" after clientID + ticket number
            if task.subject[12] != '#':
                # Parse the properties to the dictionary
                # This dict contains the ticket without a formatted date
                tickets_data = {
                    'Subject': task.subject,
                    'Category': task.categories,
                    'Date Created': task.dateCreated_property,
                    'Hours (Actual)': task.hrsActualTotal_property,
                    'Last Activity': task.datelastactivity_property
                }
                # Add to listTickets dictionary
                listTickets.append(tickets_data)
    
    # Convert the "Last Activity" timestamp to Eastern Standard Time (EST)
    # Convert to 12-hour time
    eastern_tz = timezone('America/New_York')
    for tickets_data in listTickets:
        tickets_data['Date Created'] = tickets_data['Date Created'].strftime('%Y-%m-%d %I:%M %p')
        last_activity_utc = tickets_data['Last Activity']
        last_activity_est = last_activity_utc.astimezone(eastern_tz)
        tickets_data['Last Activity'] = last_activity_est.strftime('%Y-%m-%d %I:%M %p')

    # Pass the clientID and listTickets list to html render
    return render_template('task_list_client.html', clientID=clientID, tasks=listTickets)







#######################
# Flask Configuration 
#######################
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)