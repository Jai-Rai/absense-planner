# TODO: Review functions and variables names and ensure that they
#   ..  have meaningful names that represent what they do.


import calendar
import datetime
from datetime import timedelta
from django.utils.timezone import now
from django.http import HttpResponse
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.db.models.functions import Lower
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, UpdateView
from river.models.fields.state import State
from dateutil.relativedelta import relativedelta
import recurrence

from .forms import RecurringAbsencesForm, CreateTeamForm, DeleteUserForm, AbsenceForm, AcceptPolicyForm
from .models import RecurringAbsences, Relationship, Role, Team, UserProfile, Absence

User = get_user_model()


def index(request) -> render:
    """Branched view.                       \n
    IF NOT Logged in: returns the home page \n
    ELSE: returns the calendar page """
    
    # If its the first time a user is logging in, will create an object of UserProfile model for that user.
    if not request.user.is_anonymous:
        
        if not obj_exists(request.user):

            user = find_user_obj(request.user)
        else:
            user = UserProfile.objects.filter(user=request.user)[0]

        # Until the accepted_policy field is checked, the user will keep being redirected to the policy page to accept
        if not user.accepted_policy:
            return privacy_page(request, to_accept=True)
        

    # Change: If user is logged in, will be redirected to the calendar
    if request.user.is_authenticated:       
        return all_calendar(request)
    
    return render(request, "ap_app/index.html")



def privacy_page(request, to_accept=False) -> render:

    # If true, the user accepted the policy
    if request.method == "POST":
        user = find_user_obj(request.user)
        user.accepted_policy = True
        user.save()

    # If the user has been redirected from home page to accepted policy
    elif to_accept:

        return render(request, "registration/accept_policy.html", {"form": AcceptPolicyForm()})
    
    # Viewing general policy page - (Without the acceptancy form)
    return render(request, "ap_app/privacy.html")


class SignUpView(CreateView):
    form_class = UserCreationForm
    success_url = reverse_lazy("login")
    template_name = "registration/signup.html"




@login_required
def teams_dashboard(request) -> render:
    rels = Relationship.objects.order_by(Lower("team__name")).filter(
        user=request.user, status=State.objects.get(slug="active")
    )
    invite_rel_count = Relationship.objects.filter(
        user=request.user, status=State.objects.get(slug="invited")
    ).count()
    return render(
        request,
        "teams/dashboard.html",
        {"rels": rels, "invite_count": invite_rel_count},
    )


@login_required
def create_team(request) -> render:
    if request.method == "POST":
        form = CreateTeamForm(request.POST)
        if form.name_similarity():
            # TODO: write code to tell the user that their team name is similar and to give them
            # options to change the team name.
            return HttpResponse('Debug: Did not create form because the name is too similar to another team name')

        elif form.is_valid():
            form.save()
            # Gets the created team and "Owner" Role and creates a Link between 
            # the user and their team
            created_team = Team.objects.get(name=form.cleaned_data["name"])
            assign_role = Role.objects.get(role="Owner")
            Relationship.objects.create(
                user=request.user,
                team=created_team,
                role=assign_role,
                status=State.objects.get(slug="active"),
            )
            return redirect("/teams/", {"message" : "Team successfully created."})
    else:
        form = CreateTeamForm()
    return render(request, "teams/create_team.html", {"form": form})


@login_required
def join_team(request) -> render:
    """Renders page with all teams the user is not currently in"""
    user_teams = []
    all_user_teams = Relationship.objects.all().filter(user=request.user)
    for teams in all_user_teams:
        user_teams.append(teams.team)
    all_teams = Team.objects.all().exclude(name__in=user_teams)
    return render(request, "teams/join_team.html", {"all_teams": all_teams, "joined_teams": user_teams})


@login_required
def joining_team_process(request, id, role):
    find_team = Team.objects.get(id=id)
    find_role = Role.objects.get(role=role)
    new_rel = Relationship.objects.create(
        user=request.user,
        team=find_team,
        role=find_role,
        status=State.objects.get(slug="pending"),
    )
    if not find_team.private:
        Relationship.objects.filter(id=new_rel.id).update(
            status=State.objects.get(slug="active")
        )

    return redirect("dashboard")


def team_invite(request, team_id, user_id, role):
    find_team = Team.objects.get(id=team_id)
    find_user = User.objects.get(id=user_id)
    find_role = Role.objects.get(role=role)
    Relationship.objects.create(
        user=find_user,
        team=find_team,
        role=find_role,
        status=State.objects.get(slug="invited"),
    )
    return redirect("dashboard")


@login_required
def view_invites(request):
    all_invites = Relationship.objects.filter(
        user=request.user, status=State.objects.get(slug="invited")
    )
    return render(request, "teams/invites.html", {"invites": all_invites})


@login_required
def leave_team(request, id):
    find_relationship = Relationship.objects.get(id=id)
    find_relationship.custom_delete()
    team_cleaner(find_relationship)
    return redirect("dashboard")


def team_cleaner(rel):
    team = Team.objects.get(id=rel.team.id)
    all_team_relationships = Relationship.objects.filter(team=team)
    if all_team_relationships.count() == 0:
        team.delete()
    return


@login_required
def team_settings(request, id):
    """Checks to see if user is the owner and renders the Setting page"""
    team = Team.objects.get(id=id)
    user_relation = Relationship.objects.get(team=id, user=request.user)
    if user_relation.role.role == "Owner":
        all_pending_relations = Relationship.objects.filter(
            team=id, status=State.objects.get(slug="pending")
        )
        return render(
            request,
            "teams/settings.html",
            {"team": team, "pending_rels": all_pending_relations},
        )

    return redirect("dashboard")


def joining_team_request(request, id, response):
    find_rel = Relationship.objects.get(id=id)
    if response == "accepted":
        state_response = State.objects.get(slug="active")
    elif response == "nonactive":
        state_response = State.objects.get(slug="nonactive")
    Relationship.objects.filter(id=find_rel.id).update(status=state_response)

    return redirect("dashboard")


@login_required
def add(request) -> render:
    """create new absence record"""
    if request.method == "POST":
        form = AbsenceForm(request.POST)
        if form.is_valid():
            obj = Absence()
            obj.absence_date_start = form.cleaned_data["start_date"]
            obj.absence_date_end = form.cleaned_data["end_date"]
            obj.request_accepted = False
            obj.User_ID = request.user
            obj.save()
            return render(request, "ap_app/add_absence.html", {"form" : form, "message" : "Absence successfully recorded."})
            # redirect to success page
    else:
        form = AbsenceForm()
    content = {"form": form}
    return render(request, "ap_app/add_absence.html", content)

@login_required
def add_recurring(request) -> render:
    if request.method == "POST":
        form = RecurringAbsencesForm(request.POST)
        form.instance.User_ID = request.user  
        form.save()
    else:
        form = RecurringAbsencesForm()

    content = {'form' : form}
    return render(request, "ap_app/add_recurring_absence.html", content)


@login_required
def details_page(request) -> render:
    """returns details web page"""
    # TODO: get employee details and add them to context
    context = {"employee_dicts": ""}
    return render(request, "ap_app/Details.html", context)


def get_date_data(
    month=datetime.datetime.now().strftime("%B"),
    year=datetime.datetime.now().year,
):
    #  uses a dictionary to get all the data needed for the context
    #  and concatenates it to form the full context with other dictionaries
    data = {}
    data["current_year"] = datetime.datetime.now().year
    data["current_month"] = datetime.datetime.now().strftime("%B")
    data["year"] = year
    data["month"] = month
    data["day_range"] = range(
        1,
        calendar.monthrange(
            data["year"], datetime.datetime.strptime(data["month"], "%B").month
        )[1]
        + 1,
    )
    data["month_num"] = datetime.datetime.strptime(data["month"], "%B").month

    data["previous_month"] = 0
    data["next_month"] = 0
    data["previous_year"] = data["year"] - 1
    data["next_year"] = data["year"] + 1

    # as the month number resets every year try and except statements
    # have to be used as at the end and start of a year
    # the month cannot be calculated by adding or subtracting 1
    # as 13 and 0 are not datetime month numbers
    try:
        data["next_month"] = datetime.datetime.strptime(
            str((datetime.datetime.strptime(data["month"], "%B")).month + 1), "%m"
        ).strftime("%B")
    except ValueError:
        pass
    try:
        data["previous_month"] = datetime.datetime.strptime(
            str((datetime.datetime.strptime(data["month"], "%B")).month - 1), "%m"
        ).strftime("%B")
    except ValueError:
        pass

    # calculating which days are weekends to mark them easier in the html
    data["days_name"] = []
    month = data["month"]
    year = data["year"]
    for day in data["day_range"]:
        date = f"{day} {month} {year}"
        date = datetime.datetime.strptime(date, "%d %B %Y")
        date = date.strftime("%A")[0:2]
        data["days_name"].append(date)

    return data


def get_absence_data(users, user_type):
    data = {}
    absence_content = []
    total_absence_dates = {}
    total_recurring_dates = {}
    all_absences = {}
    delta = datetime.timedelta(days=1)

    for user in users:
        # all the absences for the user
        if user_type == 1:
            user_id = user.user.id
        else:
            user_id = user.id

        absence_info = Absence.objects.filter(User_ID=user_id)
        total_absence_dates[user] = []
        all_absences[user] = []
        
        # if they have any absences
        if absence_info:
            # mapping the absence content to keys in dictionary
            for i, x in enumerate(absence_info):
                absence_id = x.ID
                absence_date_start = x.absence_date_start
                absence_date_end = x.absence_date_end
                dates = absence_date_start
                while dates <= absence_date_end:
                    total_absence_dates[user].append(dates)
                    dates += delta

                absence_content.append(
                    {
                        "ID": absence_id,
                        "absence_date_start": absence_date_start,
                        "absence_date_end": absence_date_end,
                        "dates": total_absence_dates[user],
                    }
                )

            # for each user it maps the set of dates to a dictionary key labelled as the users name
            total_absence_dates[user] = total_absence_dates[user]
            all_absences[user] = absence_content

        recurring = RecurringAbsences.objects.filter(User_ID=user_id)
        total_recurring_dates[user] = []
        if recurring:
            for recurrence_ in recurring:
                dates = recurrence_.Recurrences.occurrences(dtend = datetime.datetime.strptime(str(datetime.datetime.now().year + 2),"%Y"))
                for x in list(dates)[:-1]:
                    time_const = "23:00:00"
                    time_var = datetime.datetime.strftime(x, "%H:%M:%S")
                    if time_const == time_var:
                        x = x + timedelta(hours=2)
                    total_recurring_dates[user].append(x) 
        
    data["recurring_absence_dates"] = total_recurring_dates
    data["all_absences"] = all_absences
    data["absence_dates"] = total_absence_dates
    data["users"] = users
    return data


@login_required
def team_calendar(
    request,
    id,
    month=datetime.datetime.now().strftime("%B"),
    year=datetime.datetime.now().year,
):
    data_1 = get_date_data(month, year)

    users = Relationship.objects.all().filter(
        team=id, status=State.objects.get(slug="active")
    )
    
    
    data_2 = get_absence_data(users, 1)

    team = Team.objects.get(id=id)

    user_in_teams = []
    for rel in Relationship.objects.filter(team=team):
        user_in_teams.append(rel.user.id)
        
    

    data_3 = {
        "owner":Role.objects.all()[0],
        "Sa": "Sa",
        "Su": "Su",
        "current_user": Relationship.objects.get(user=request.user, team=team),
        "team": team,
        "all_users": User.objects.all().exclude(id__in=user_in_teams),
        "team_count": Relationship.objects.filter(
            team=team.id, status=State.objects.get(slug="active")
        ).count(),
    }

    context = {**data_1, **data_2, **data_3}
    return render(request, "teams/calendar.html", context)


@login_required
def all_calendar(
    request,
    month=datetime.datetime.now().strftime("%B"),
    year=datetime.datetime.now().year,
):
    data_1 = get_date_data(month, year)

    all_users = []
    all_users.append(request.user)
    user_relations = Relationship.objects.filter(user=request.user)
    

    #NOTE: need to convert filtered queryset back to list for "all_users"
    for relation in user_relations:
        rels = Relationship.objects.filter(
            team=relation.team, status=State.objects.get(slug="active")
        )
        for rel in rels:
            if rel.user in all_users:
                pass
            else:
                all_users.append(rel.user)
    
    

    #Filtering
    filtered_users = []
    # Filtering by both username & absence
    if "username" in request.GET and "absent" in request.GET:
        # Get username input & limits the length to 50
        name_filtered_by = request.GET["username"][:50]
        for absence in Absence.objects.all():
            user = User.objects.get(id=absence.User_ID.id)
            if user in all_users:
                username = user.username
                if not absence.User_ID in filtered_users and name_filtered_by.lower() in username.lower():
                    filtered_users.append(absence.User_ID)


    # ONLY filtering by username
    elif "username" in request.GET:
        # Name limit is 50 
        name_filtered_by = request.GET["username"][:50]
        for user in all_users:
            # same logic as "icontains", searches through users names & finds similarities
            if name_filtered_by.lower() in user.username.lower():
                filtered_users.append(user)

        


    # ONLY filtering by absences
    elif "absent" in request.GET:
        for absence in Absence.objects.all():
            user = User.objects.get(id=absence.User_ID.id)
            if user in all_users:
                username = user.username
                if not absence.User_ID in filtered_users:
                    filtered_users.append(absence.User_ID) 

    # Else, no filtering
    else:
        filtered_users = all_users
    
    
    # NOTE: Are these necessary here? Not in use
    absence_content = []
    total_absence_dates = {}
    all_absences = {}
    delta = datetime.timedelta(days=1)
 

    data_2 = get_absence_data(all_users, 2)

    data_3 = {"Sa": "Sa", "Su": "Su","users_filter": filtered_users}

    context = {**data_1, **data_2, **data_3}
    

    return render(request, "ap_app/calendar.html", context)


# Profile page
@login_required
def profile_page(request):
    absences = Absence.objects.filter(User_ID=request.user.id)
    return render(request, "ap_app/profile.html", {"absences": absences})


@login_required
def deleteuser(request):
    """delete a user account"""
    if request.method == "POST":
        delete_form = DeleteUserForm(request.POST, instance=request.user)
        user = request.user
        user.delete()
        messages.info(request, "Your account has been deleted.")
        return redirect("index")
    else:
        delete_form = DeleteUserForm(instance=request.user)

    context = {"delete_form": delete_form}

    return render(request, "registration/delete_account.html", context)


@login_required
def absence_delete(request, absence_id: int):
    absence = Absence.objects.get(pk=absence_id)
    user = request.user
    if user == absence.User_ID:
        absence.delete()
        return redirect("profile")
    else:
        raise Exception()


class EditAbsence(UpdateView):
    template_name = "ap_app/edit_absence.html"
    model = Absence

    # specify the fields
    fields = ["absence_date_start", "absence_date_end"]

    def get_success_url(self) -> str:
        return reverse("profile")


@login_required
def profile_settings(request) -> render:
    """returns the settings page"""
    absences = Absence.objects.filter(User_ID=request.user.id)
    context = {"absences": absences}
    return render(request, "ap_app/settings.html", context)


@login_required
def add_user(request) -> render:
    if request.method == "POST":
        username = request.POST.get("username")
        try:
            absence: Absence = Absence.objects.filter(User_ID=request.user.id)[0]
        except IndexError:
            # TODO Create error page
            return redirect("/")

        try:
            user = User.objects.filter(username=username)[0]
        except IndexError:
            # TODO Create error page
            return redirect("/")

        absence.edit_whitelist.add(user)
        absence.save()
    return redirect("/profile/settings")




def find_user_obj(user_to_find):
    """ Finds & Returns object of 'UserProfile' for a user 
    \n-param (type)User user_to_find 
    """    
    users = UserProfile.objects.filter(user=user_to_find)    
    # If cannot find object for a user, than creates on
    if users.count() <= 0:
        UserProfile.objects.create(
        user = user_to_find,
        accepted_policy = False
        )

    # Users object
    user_found = UserProfile.objects.filter(user=user_to_find)[0]

    return user_found


def obj_exists(user):
    """ Determines if a user has a 'UserProfile' Object"""
    objs = UserProfile.objects.filter(user=user)
    if objs.count() == 0:
        return False

    return True 

   
      