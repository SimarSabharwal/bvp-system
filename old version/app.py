from flask import Flask, render_template, request, redirect, session
from datetime import datetime

app = Flask(__name__)
app.secret_key = "BVP_ERP_SECRET"

# ==========================================================
# STUDENTS
# ==========================================================

STUDENTS = {

    "0251BCA001": {
        "password": "1234",
        "name": "Student Morning",
        "shift": "M"
    },

    "0251BCA101": {
        "password": "1234",
        "name": "Student Afternoon",
        "shift": "A"
    }

}

# ==========================================================
# FACULTY
# ==========================================================

FACULTY = {

    "MKC": {
        "password": "mkc123",
        "name": "Dr. Mahesh Kumar Chaubey"
    }

}

# ==========================================================
# SUBJECTS
# ==========================================================

SUBJECTS = {

    "JP": "Java Programming",
    "OS": "Operating Systems",
    "SE": "Software Engineering",
    "ST": "Statistics",
    "SUM": "Start-up Management",
    "LAB JP": "Java Programming Lab",
    "LAB ORACLE": "Oracle Lab",
    "YOGA": "Yoga & Meditation",
    "BREAK": "Break"

}

# ==========================================================
# FACULTY NAMES
# ==========================================================

FACULTY_NAME = {

    "MGS": "Dr. Megha Sehgal",
    "MAG": "Dr. Mansi Agnihotri",
    "DSB": "Dr. Daljeet Singh Bawa",
    "UG": "Dr. Usha Gupta",
    "MKC": "Dr. Mahesh Kumar Chaubey",
    "AK": "Dr. Ajay Kumar",
    "AKR": "Mr. Amit Kumar",
    "YK": "Mr. Yashwant Kumar",
    "NPN": "Mr. Nripesh Kumar"

}

# ==========================================================
# REGISTERED USERS (Runtime Only)
# ==========================================================

REGISTERED_STUDENTS = {}
REGISTERED_FACULTY = {}

# ==========================================================
# TIMETABLE
# (Replace/add remaining days in Part 2)
# ==========================================================

MORNING = {

    "Monday":[
        {"start":"09:10","end":"10:05","subject":"LAB JP","faculty":"MGS","room":"AK108"},
        {"start":"10:10","end":"11:05","subject":"JP","faculty":"MGS","room":"AK108"},
        {"start":"11:05","end":"11:20","subject":"BREAK","faculty":"","room":""},
        {"start":"11:20","end":"12:15","subject":"OS","faculty":"MAG","room":"UG104"},
        {"start":"12:20","end":"01:15","subject":"LAB ORACLE","faculty":"MKC","room":"FF LAB"}
    ],

    "Tuesday":[
        {"start":"09:10","end":"10:05","subject":"SUM","faculty":"AK","room":"108"},
        {"start":"10:10","end":"11:05","subject":"SE","faculty":"DSB","room":"109"},
        {"start":"11:05","end":"11:20","subject":"BREAK","faculty":"","room":""},
        {"start":"11:20","end":"12:15","subject":"LAB JP","faculty":"MGS","room":"AK108"},
        {"start":"12:20","end":"01:15","subject":"YOGA","faculty":"AKR","room":"108"}
    ],

    "Wednesday":[
        {"start":"09:10","end":"10:05","subject":"LAB ORACLE","faculty":"MKC","room":"FF LAB"},
        {"start":"10:10","end":"11:05","subject":"OS","faculty":"MAG","room":"UG104"},
        {"start":"11:05","end":"11:20","subject":"BREAK","faculty":"","room":""},
        {"start":"11:20","end":"12:15","subject":"JP","faculty":"MGS","room":"AK108"},
        {"start":"12:20","end":"01:15","subject":"ST","faculty":"UG","room":"UG104"}
    ],

    "Thursday":[
        {"start":"09:10","end":"10:05","subject":"JP","faculty":"MGS","room":"AK108"},
        {"start":"10:10","end":"11:05","subject":"SE","faculty":"DSB","room":"109"},
        {"start":"11:05","end":"11:20","subject":"BREAK","faculty":"","room":""},
        {"start":"11:20","end":"12:15","subject":"SUM","faculty":"AK","room":"108"},
        {"start":"12:20","end":"01:15","subject":"ST","faculty":"UG","room":"UG104"}
    ],

    "Friday":[
        {"start":"09:10","end":"10:05","subject":"ST","faculty":"UG","room":"UG104"},
        {"start":"10:10","end":"11:05","subject":"OS","faculty":"MAG","room":"UG104"},
        {"start":"11:05","end":"11:20","subject":"BREAK","faculty":"","room":""},
        {"start":"11:20","end":"12:15","subject":"SE","faculty":"DSB","room":"109"},
        {"start":"12:20","end":"01:15","subject":"YOGA","faculty":"AKR","room":"108"}
    ],

    "Saturday":[]
}

AFTERNOON = {

    "Monday":[
        {"start":"01:20","end":"02:15","subject":"ST","faculty":"YK","room":"UG104"},
        {"start":"02:15","end":"03:10","subject":"SUM","faculty":"AK","room":"108"},
        {"start":"03:10","end":"03:35","subject":"BREAK","faculty":"","room":""},
        {"start":"03:35","end":"04:30","subject":"JP","faculty":"NPN","room":"AK108"},
        {"start":"04:30","end":"05:25","subject":"OS","faculty":"DSB","room":"UG104"}
    ],

    "Tuesday":[
        {"start":"01:20","end":"02:15","subject":"YOGA","faculty":"AKR","room":"108"},
        {"start":"02:15","end":"03:10","subject":"ST","faculty":"YK","room":"UG104"},
        {"start":"03:10","end":"03:35","subject":"BREAK","faculty":"","room":""},
        {"start":"03:35","end":"04:30","subject":"LAB ORACLE","faculty":"MKC","room":"FF LAB"},
        {"start":"04:30","end":"05:25","subject":"SE","faculty":"MAG","room":"109"}
    ],

    "Wednesday":[
        {"start":"01:20","end":"02:15","subject":"LAB JP","faculty":"NPN","room":"AK108"},
        {"start":"02:15","end":"03:10","subject":"JP","faculty":"NPN","room":"AK108"},
        {"start":"03:10","end":"03:35","subject":"BREAK","faculty":"","room":""},
        {"start":"03:35","end":"04:30","subject":"SUM","faculty":"AK","room":"108"},
        {"start":"04:30","end":"05:25","subject":"SE","faculty":"MAG","room":"109"}
    ],

    "Thursday":[
        {"start":"01:20","end":"02:15","subject":"LAB JP","faculty":"NPN","room":"AK108"},
        {"start":"02:15","end":"03:10","subject":"JP","faculty":"NPN","room":"AK108"},
        {"start":"03:10","end":"03:35","subject":"BREAK","faculty":"","room":""},
        {"start":"03:35","end":"04:30","subject":"LAB ORACLE","faculty":"MKC","room":"FF LAB"},
        {"start":"04:30","end":"05:25","subject":"OS","faculty":"DSB","room":"UG104"}
    ],

    "Friday":[
        {"start":"01:20","end":"02:15","subject":"YOGA","faculty":"AKR","room":"108"},
        {"start":"02:15","end":"03:10","subject":"ST","faculty":"YK","room":"UG104"},
        {"start":"03:10","end":"03:35","subject":"BREAK","faculty":"","room":""},
        {"start":"03:35","end":"04:30","subject":"OS","faculty":"DSB","room":"UG104"},
        {"start":"04:30","end":"05:25","subject":"SE","faculty":"MAG","room":"109"}
    ],

    "Saturday":[]
}

# ==========================================================
# DATE & TIME HELPERS
# ==========================================================

def current_day():
    return datetime.now().strftime("%A")


def current_time():
    return datetime.now().strftime("%H:%M")


def timetable(shift):
    return MORNING if shift == "M" else AFTERNOON


def todays_schedule(shift):
    return timetable(shift).get(current_day(), [])


# ==========================================================
# STUDENT HELPERS
# ==========================================================

def current_class(shift):

    now = current_time()

    for cls in todays_schedule(shift):

        if cls["start"] <= now < cls["end"]:

            return {

                "subject": SUBJECTS.get(cls["subject"], cls["subject"]),

                "faculty": FACULTY_NAME.get(
                    cls["faculty"],
                    cls["faculty"]
                ),

                "faculty_code": cls["faculty"],

                "room": cls["room"],

                "start": cls["start"],

                "end": cls["end"]

            }

    return None


def next_class(shift):

    now = current_time()

    for cls in todays_schedule(shift):

        if cls["start"] > now:

            return {

                "subject": SUBJECTS.get(cls["subject"], cls["subject"]),

                "faculty": FACULTY_NAME.get(
                    cls["faculty"],
                    cls["faculty"]
                ),

                "faculty_code": cls["faculty"],

                "room": cls["room"],

                "start": cls["start"],

                "end": cls["end"]

            }

    return None


# ==========================================================
# FACULTY HELPERS
# ==========================================================

def faculty_schedule(code):

    data = []

    for shift_name, table in {

        "Morning": MORNING,

        "Afternoon": AFTERNOON

    }.items():

        for cls in table.get(current_day(), []):

            if cls["faculty"] == code:

                data.append({

                    "shift": shift_name,

                    "subject": SUBJECTS.get(
                        cls["subject"],
                        cls["subject"]
                    ),

                    "room": cls["room"],

                    "start": cls["start"],

                    "end": cls["end"]

                })

    data.sort(key=lambda x: x["start"])

    return data


def faculty_current(code):

    now = current_time()

    for cls in faculty_schedule(code):

        if cls["start"] <= now < cls["end"]:

            return cls

    return None


def faculty_next(code):

    now = current_time()

    for cls in faculty_schedule(code):

        if cls["start"] > now:

            return cls

    return None


# ==========================================================
# HOME
# ==========================================================

@app.route("/")
def home():
    return render_template("index.html")


# ==========================================================
# STUDENT REGISTER
# ==========================================================

@app.route("/student/register", methods=["GET", "POST"])
def student_register():

    if request.method == "POST":

        erp = request.form["erp_id"].strip()

        STUDENTS[erp] = {

            "name": request.form["name"],

            "password": request.form["password"],

            "shift": request.form["shift"]

        }

        return redirect("/student/login")

    return render_template("student_register.html")


# ==========================================================
# FACULTY REGISTER
# ==========================================================

@app.route("/faculty/register", methods=["GET", "POST"])
def faculty_register():

    if request.method == "POST":

        code = request.form["faculty_code"].upper().strip()

        FACULTY[code] = {

            "name": request.form["name"],

            "password": request.form["password"]

        }

        return redirect("/faculty/login")

    return render_template("faculty_register.html")


# ==========================================================
# STUDENT LOGIN
# ==========================================================

@app.route("/student/login", methods=["GET", "POST"])
def student_login():

    if request.method == "POST":

        erp = request.form["erp_id"].strip()

        password = request.form["password"].strip()

        if erp in STUDENTS:

            if STUDENTS[erp]["password"] == password:

                session["role"] = "student"

                session["erp"] = erp

                return redirect("/student/dashboard")

        return render_template(

            "student_login.html",

            error="Invalid ERP ID or Password"

        )

    return render_template("student_login.html")


# ==========================================================
# FACULTY LOGIN
# ==========================================================

@app.route("/faculty/login", methods=["GET", "POST"])
def faculty_login():

    if request.method == "POST":

        code = request.form["faculty_code"].upper().strip()

        password = request.form["password"].strip()

        if code in FACULTY:

            if FACULTY[code]["password"] == password:

                session["role"] = "faculty"

                session["faculty"] = code

                return redirect("/faculty/dashboard")

        return render_template(

            "faculty_login.html",

            error="Invalid Faculty Credentials"

        )

    return render_template("faculty_login.html")
# ==========================================================
# STUDENT DASHBOARD
# ==========================================================

@app.route("/student/dashboard")
def student_dashboard():

    if "erp" not in session:

        return redirect("/student/login")

    student = STUDENTS[session["erp"]]

    shift = student["shift"]

    return render_template(

        "student_dashboard.html",

        student=student,

        current=current_class(shift),

        upcoming=next_class(shift),

        timetable=todays_schedule(shift),

        day=current_day(),

        now=current_time()

    )


# ==========================================================
# FACULTY DASHBOARD
# ==========================================================

@app.route("/faculty/dashboard")
def faculty_dashboard():

    if "faculty" not in session:

        return redirect("/faculty/login")

    code = session["faculty"]

    return render_template(

        "faculty_dashboard.html",

        faculty=FACULTY[code],

        current=faculty_current(code),

        upcoming=faculty_next(code),

        timetable=faculty_schedule(code),

        day=current_day(),

        now=current_time()

    )


# ==========================================================
# LOGOUT
# ==========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


# ==========================================================
# ERROR PAGES
# ==========================================================

@app.errorhandler(404)
def page_not_found(e):

    return "<h2>404 - Page Not Found</h2>",404


@app.errorhandler(500)
def server_error(e):

    return "<h2>Internal Server Error</h2>",500


# ==========================================================
# RUN APPLICATION
# ==========================================================

if __name__ == "__main__":

    app.run(

        debug=True,

        host="127.0.0.1",

        port=5000

    )