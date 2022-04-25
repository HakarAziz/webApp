
from flask import Flask, request, flash, url_for, redirect, render_template, session
import pymysql
from datetime import timedelta
import time
from threading import Thread
import datetime
import os
from werkzeug.utils import secure_filename

#Denna gör så vi kan ladda upp bilder från hemsidan , dvs böckernas framsida.
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'}


#Skapar en instans av flask
app = Flask(__name__)
#nyckel så vi kan ha sessioner, dvs nyckel.
#Vi kan också bestämma hur länge sessions data ska spara hos servern.
app.secret_key = "TJOOO"
app.permanent_session_lifetime = timedelta(minutes=30)
app.config["IMAGE_UPLOADS"] = "/var/www/webApp/webApp/static/"
#Måste ha         session.permanent = True också när vi skapar sessionen för att den ska följa reglerna.


#Istället för mysql db kunde man använt flask, men nu använder vi mysql.
connection = pymysql.connect(host='dsd400.port0.org',
    user='pyEG',
    password='asd123454321'.encode().decode('latin1'),
    database='Library',
    charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor)

#Check av databasen vid start om det ligger kvar böcker som resv=1 bok=0, dvs bara om servern har kraschat.
def dataBaseStartUpCheck():
    print("Kör database check för resv böcker om det har kraschat")
    cursor = connection.cursor()
    cursor.execute("DELETE FROM Library.Bokningar WHERE Bok_reserved='1' and Bok_booked='0' ")
    connection.commit()
    cursor.close()
    return

dataBaseStartUpCheck()



#Index route, när man först går in på hemsidan.
@app.route("/")
def index():
    if "user" in session:
        user = session["user"]
        return redirect(url_for("user"))
    else:
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM Library.Books LEFT JOIN Library.Bokningar ON Library.Books.idBooks = Library.Bokningar.idBooks")
        data_books = cursor.fetchall()
        return render_template("index.html", Data = data_books)


#Utloggning, man tar bort sessionsdata från sessions dict och blir utloggad från hemsidan.
@app.route("/logout")
def logout():
    if "user" in session:
        user = session["user"]
        #Flash medd, typ litet medd som kommer ut.  #warning, info och errors
        #med f string, dvs f före kan vi ha med oss variabler frn flask/jinsu2.
        flash(f"You have succesfully logged out, {user}", "info")
    session.pop("user", None)
    return redirect(url_for("login"))


#Inloggning, sätter session namnet på "user" till användarens, på så sätt kan vi autentisera användaren.
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == "POST":
        session.permanent = True
        #request.form är ju dict.
        user = request.form['username']
        passwd = request.form['password']
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM Library.Users WHERE User='" + user + "' and Password='" + passwd + "'")
        data = cursor.fetchone()
        if data is None:
            flash("Fel anvandarnamn eller losenord, prova igen eller skapa ett nytt konto x)")
            return render_template("login.html")
        else:
            print(data)
            userID = data['Uid']
            #vanlig dict som vi kan printa med osv och jämföra..
            print(data['User'])
            session["user"] = user
            session["userID"] = userID
            print("testar att printa session")
            print(session["user"], session["userID"])
            return redirect(url_for("user"))
        #session sparar data som dict igen, det är ju exakt likadant. här är "user" = user dvs det vi skriver in i variabeln user.

    else:
        if "user" in session:
            return redirect(url_for("user"))
        return render_template("login.html")

#Skapa en användare emot databasen, lägger bara till i "user" tabellen helt enkelt, först lite check så vi ej får duplicerade användare.
@app.route('/register', methods=['GET', 'POST'])
def register():
    if "user" in session:
        return redirect(url_for("user"))
    else:
        if request.method == "POST":
            usernames = request.form['username']
            passwd = request.form['password']
            email = request.form['Email']
            person_nr = request.form['personNummer']
            cursor = connection.cursor()
            cursor.execute("SELECT * FROM Library.Users WHERE User='" + usernames + "'")
            data = cursor.fetchone()
            if data is None:
                sql = "INSERT INTO Library.Users (User, Email, User_personal_number, Password) VALUES (%s, %s, %s, %s)"
                val = (usernames, email, person_nr, passwd)
                cursor.execute(sql, val)
                connection.commit()
                cursor.close()
                return redirect(url_for("login"))
            else:
                flash("Användaren existerar redan!")
    return render_template('register.html')


#Stegvis på hur funktionen fungerar: 1.Kolla så user är i session, 2.Kolla så boken inte är reserverad och inte bokad av någon annan.
#Boken ska liggas i "Bokningar tabellen" om den är reserverad elelr bokad.
#Om ALLT är okej så ska en timer startas som sätter att boken är reserverad av X användare i Y minuter.
#Om man inte har bokat innan timern är ute så returneras man tillbaka ?
#Klickar man på knappen så ska man kunna bekräfta att den ska bokas dvs.. reserverad=0, bokad=1.
#Här skickar vi med "bokid" parameter för att försöka bara, fungerar exakt likdant som att använda request.args("bokID") men vi ville prova.
@app.route('/bokning/<string:bokid>', methods=['GET', 'POST'])
def bokning(bokid):
    if "user" in session:
        user = session["user"]
        userID = str(session["userID"])
        print("printar userID")
        print(userID)
        print("Printar nya bok_id värde:" + bokid)
        #Kollar först om boken är bokad, sedan reserverad och om flera klickar samtidigt har vi FOR UPDATE.
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM Library.Bokningar WHERE idBooks='" + bokid + "' and Bok_booked='1'")
        data = cursor.fetchone()
        if data is not None:
            flash("Tyvärr så är boken bokad!")
            return redirect(url_for("user"))
        else:
            #Kollar först om boken är bokad över, sedan under reserverad och om flera klickar samtidigt har vi FOR UPDATE.
            print("bok_id" + bokid + " kund_id=" + userID)
            cursor.execute("SELECT * FROM Library.Bokningar WHERE idBooks='" + bokid + "' and Bok_reserved='1' FOR UPDATE")
            data = cursor.fetchone()
            if data is not None:
                flash("Tyvärr så är boken redan reserverad!")
                return redirect(url_for("user"))
            else:
                #Starta en ny tråd som kör resvTimer funktionen.
                cursor.execute("SELECT * FROM Library.Books WHERE idBooks='" + bokid + "'")
                data_om_bok = cursor.fetchone()
                bokID = data_om_bok['idBooks']
                connection.commit()
                cursor.close()
                thread = Thread(target=resvTimer, args=(userID, bokID, ))
                thread.start()
                return render_template("bokning.html", data_om_boken = data_om_bok, test = bokID)     
    else:
        return redirect(url_for("login"))



#Denna funktion reserverar boken för en användare in i databasen, om användaren ej har bekräftat sin bokning så tar den bort reservationen.
#Denna verkligen bokar bokar i X min, gör en grej? sedan time.sleep(30), sedan så ändrar den i databasen.
def resvTimer(userID, bokID):
    cursor = connection.cursor()
    userIDSTR = str(userID)
    bokIDSTR = str(bokID)
    print(userIDSTR, bokIDSTR)

    #bokaboken ska sätta boken vi ska boka till reserverad=0 och Bok_booked=1.
    #Först skapa en rad, sedan uppdaterar vi för våran FOR UPDATE ska fungera korrekt.
    sql = "INSERT INTO Library.Bokningar (Uid, idBooks, Bok_reserved, Bok_booked) VALUES (%s, %s, %s, %s)"
    val = (userID, bokID, '0', '0')
    cursor.execute(sql, val)
    connection.commit()
    cursor.execute("UPDATE Library.Bokningar SET Bok_reserved='1' WHERE idBooks ='"+ bokIDSTR +"'")
    connection.commit()
    cursor.close()
    print("Reserverad bok i bokningar:", userIDSTR, bokIDSTR)

    #Här har vi värdet på hur länge man ska kunna reserva en bok.
    time.sleep(30)

    #Kollar om boken är bokad. 
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM Library.Bokningar WHERE idBooks='" + bokIDSTR + "' and Bok_reserved='1' and Bok_booked='0' and Uid='" + userIDSTR +  "'")
    data = cursor.fetchone()
    connection.commit()
    if data is not None:
        #Användare har ej bekräftat bokning, då tar vi bort den från BOKNINGAR.
        cursor.execute("DELETE FROM Library.Bokningar WHERE idBooks='" + bokIDSTR + "'")
        connection.commit()
        cursor.close()
        print("Vi tog bort från databasen pga ej bokad")



#Bekräftning av boken! Samt kollar så ingen annan användare kan gå t.ex in på en länk och bekräfta för en och allt. Bokningen kan vara ske av korrekt användarID för korrekt bokID.
@app.route('/bokaboken', methods=['GET', 'POST'])
def bokaboken():
    if "user" in session:
        userID = str(session["userID"])
        user = session["user"]
        bok_id = request.args.get('idBooks')
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM Library.Bokningar WHERE idBooks='" + bok_id + "' and Uid='" + userID +  "'")
        data = cursor.fetchone()
        if data is None:
            flash("Tiden för att reservera boken har tyvärr runnit ut, gör om processen för att försöka boka boken\n Eller så försöker du boka för någon annan ;)")
            cursor.execute("SELECT * FROM Library.Books")
            data_books = cursor.fetchall()
            connection.commit()
            cursor.close()
            return redirect(url_for("user"))
        else:
            now = datetime.datetime.now()
            tidVARSTART = str(now.year)+"/"+str(now.month)+"/"+str(now.day)
            newDate = (now.day+2)
            tidVAREND = str(now.year)+"/"+str(now.month)+"/"+str(newDate)

            print("testar att printa bokabokden bok_id " + bok_id)
            cursor.execute("UPDATE Library.Bokningar SET Bok_Reserved='0', Bok_Booked='1', Bok_booked_datumSTART='" + tidVARSTART + "', Bok_booked_datumEND='" +  tidVAREND  + "' WHERE idBooks='" + bok_id + "'")
            connection.commit()

            cursor.execute("SELECT * FROM Library.Books WHERE idBooks='" + bok_id + "'")
            data_om_bok = cursor.fetchone()
            connection.commit()
            cursor.close()
            return render_template('bokaboken.html', data_om_bok=data_om_bok, user=user, tidVARSTART = tidVARSTART, tidVAREND = tidVAREND )
    else:
        return redirect(url_for("login"))


#Se vilka bokningar man har helt enkelt. Hämtar och matchar med ens användarID med de som är i bokningar.
@app.route('/bokningar', methods=['GET', 'POST'])
def bokningar():
    if "user" in session:
        userIDSTR = str(session["userID"])
        user = session["user"]
        
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM Library.Books LEFT JOIN Library.Bokningar ON Library.Books.idBooks = Library.Bokningar.idBooks  WHERE Bok_booked='1' and Uid='" + userIDSTR +  "'")
        data_books = cursor.fetchall()
        connection.commit()
        cursor.close()
        return render_template("bokningar.html", user=user, Data_books=data_books)
    else:
        return redirect(url_for("login"))

#Avbokning funktion, så man kan klicka för att avboka en bok så den är tillbaka i systemet som ej bokad och en annan användare kan boka.
#Vanlig användare och admin har olika avbokningsfunktioner.
@app.route('/avbokning', methods=['GET', 'POST'])
def avbokning():
    if "user" in session:
        userID = str(session["userID"])
        user = session["user"]
        bok_id = request.args.get('idBooks')
        bok_namn = str(request.args.get('bookName'))
        print(bok_namn)
        cursor = connection.cursor()
        cursor.execute("DELETE FROM Library.Bokningar WHERE idBooks='" + bok_id + "'")
        connection.commit()
        cursor.close()
        #deta går ju! 

        flash("Boken" + bok_namn + " är nu återlämnad")
        if user == 'Admin':
            return redirect(url_for("hanterabokningar"))
        else:
            return redirect(url_for("bokningar"))
    else:
        return redirect(url_for("login"))


#Profil helt enkelt, så man kan hämta data om sin användare, ändra lösenord osv.
@app.route('/profil', methods=['GET', 'POST'])
def profil():
    if "user" in session:
        user = session["user"]
        userID = str(session["userID"])
        cursor = connection.cursor()
        #cursor.execute("SELECT * FROM Library.Bokningar WHERE Bok_booked='1' and Uid='" + userID +  "'")
        cursor.execute("SELECT * FROM Library.Books LEFT JOIN Library.Bokningar ON Library.Books.idBooks = Library.Bokningar.idBooks  WHERE Bok_booked='1' and Uid='" + userID +  "'")
        data_books = cursor.fetchall()
        cursor.execute("SELECT * FROM Library.Users WHERE Uid='" + userID +  "'")
        data_user = cursor.fetchall()
        cursor.execute("SELECT * FROM Library.Books")
        data = cursor.fetchall()
        return render_template("profil.html", user=user, userID = userID, Data = data, Data_books=data_books, Data_user = data_user)
    else:
        return redirect(url_for("login"))


#Bara som admin kan se detta, alla bokningar för alla användare. Möjligt att avboka för andra.
@app.route('/hanterabokningar', methods=['GET', 'POST'])
def hanterabokningar():
    if "user" in session:
        user = session["user"]
        if user == 'Admin':
            user = session["user"]
            #Här kan man ju snygga till och t.ex ha JOIN på dem, så det matchar ist för att ha en ifsats i hanterabokningar.html som matchar.
            #Det som vi vill kolla är ju den som har Bok_booked=1, hämta bokid och hämta bokid från Library.books.
            cursor = connection.cursor()
            cursor.execute("SELECT * FROM Library.Books LEFT JOIN Library.Bokningar ON Library.Books.idBooks = Library.Bokningar.idBooks LEFT JOIN Library.Users ON Library.Users.UID = Library.Bokningar.Uid WHERE Bok_booked='1'")
            data_books = cursor.fetchall()
            connection.commit()
            cursor.close()
            return render_template("hanterabokningar.html", user=user, Data_books=data_books)
            #return render_template("hanterabokningar.html", user=user, Data = data, Data_books=data_books)
        else:
            flash('Där får du inte gå in, bara admin')
            return redirect(url_for("user")) 
    else:
        return redirect(url_for("login"))   

#Funktion som leder till att hantera böcker sida för en admin, detta är t.ex att lägga till böcker helt enkelt.. vidarefunktion finns under då detta är grunden för den sidan.
@app.route('/hanterabocker', methods=['GET', 'POST'])
def hanterabocker():
    if "user" in session:
        user = session["user"]
        if user == 'Admin':
            return render_template("hanterabocker.html", user=user)
        else:
            flash('Där får du inte gå in x)')
            return redirect(url_for("user")) 
    else:
        return redirect(url_for("login"))   



#Funktion som ser till att filer med endast de filändelser som vi tillåter kan läggas till, säkerhetsåtgärd, import secure_filename högst upp.
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

#funktionen då som lägger till en bok i detta fall, hämtar data från input och lägger till, samt sparar en bild som tillhör en bok.
@app.route('/add_book', methods=['GET', 'POST'])
def add_book():
    if "user" in session:
            user = session["user"]
            if request.method == "POST":
                tit = request.form['Title']
                auth = request.form['Author']
                publi = request.form['Publisher']
                file = request.files['image']
                filnamn = file.filename
                
                cursor = connection.cursor()
                cursor.execute("SELECT * FROM Library.Books WHERE Name='" + tit + "'")
                data = cursor.fetchone()
                if data is None:
                        sql = "INSERT INTO Library.Books (Name, Author, Publisher, Image_name) VALUES (%s, %s, %s, %s)"
                        val = (tit, auth, publi, filnamn)
                        cursor.execute(sql, val)
                        if file and allowed_file(file.filename):
                            filename = secure_filename(file.filename)
                            file.save(os.path.join(app.config['IMAGE_UPLOADS'], filename))
                        connection.commit()
                        cursor.close()
                        return render_template("add_book.html", user = user)
                else:
                    flash("Denna bok finns redan i databasen!")
    else:
        return redirect(url_for("login"))
    return render_template('add_book.html')



#Sökfunktion, kan söka inloggad eller utloggad och se böcker som vi har.
@app.route('/search', methods=['GET', 'POST'])
def search():
        if request.method == "POST":
            search_string = request.form['searchie']
            cursor = connection.cursor()
            print(search_string)
            cursor.execute("SELECT * FROM Library.Books WHERE Name LIKE '%"+ search_string + "%' or Author LIKE '%"+ search_string + "%' ")
            results = cursor.fetchall()
            connection.commit()
            cursor.close()
            search_hit = len(results)
            return render_template("search.html", Results = results, Hits = search_hit, ss = search_string)

#user, dvs detta är den som man redirekteras till när man är inloggad. Det är då man ser "boka bok" istället för att "logga in för att boka.." osv.
#Direkt kopia av index fast man är inloggad.
@app.route("/user")
def user():
    if "user" in session:
        userID = session["userID"]
        user = session["user"]
        cursor = connection.cursor()
        #cursor.execute("SELECT * FROM Library.Books")
        cursor.execute("SELECT * FROM Library.Books LEFT JOIN Library.Bokningar ON Library.Books.idBooks = Library.Bokningar.idBooks")
        data_books = cursor.fetchall()
        connection.commit()
        cursor.close()

        #print(data_books)
        return render_template("user.html", user=user, Data=data_books)
    else:
        return redirect(url_for("login"))

#Funktion som gör det möjligt att kunna klicka på en författares namn och filtrera efter det. T.ex klicka på Astrid Lindgren så kommer alla böcker av Astrid upp.
@app.route("/AuthorInfo/<string:TheAuthor>", methods=['GET', 'POST'])
def AuthorInfo(TheAuthor):
    cursor = connection.cursor()            
    cursor.execute("Select * FROM Library.Books WHERE Author='" + TheAuthor + "'")
    AuthorsBooks = cursor.fetchall()
    AuthorsBooksAntal = len(AuthorsBooks)
    connection.commit()
    cursor.close()
    return render_template("Author.html", AuthorsBooks = AuthorsBooks, AuthorsBooksAntal = AuthorsBooksAntal)


#Funktion som ändrar lösenord, först ser till så att man matchar med gamla lösenordet så man sedan kan ändra till ett nytt.
@app.route('/newpasswd', methods=['GET', 'POST'])
def newpasswd():
    if "user" in session:   
        user = session['user']
        userID = str(session['userID'])
        print("framme")
        if request.method == "POST":
            print("nej")
            passwd = request.form['currentPasswd']
            newpasswd1 = request.form['newPasswd1']
            newpasswd2 = request.form['newPasswd2']

            cursor = connection.cursor()            
            cursor.execute("Select * FROM Library.Users WHERE Uid='" + userID + "'")
            dataUid = cursor.fetchone()

            print(dataUid)
            if (newpasswd1== newpasswd2):
                if (dataUid['Password'] == passwd):
                    #cursor = connection.cursor()
                    #cursor.execute("DELETE * FROM Library.Users WHERE Password='" + currentPasswd + "'")
                    sql = ("UPDATE Library.Users SET Password = '" + newpasswd1 + "' WHERE Uid = '" + userID+ "'")
                    cursor.execute(sql)
                    connection.commit()
                    cursor.close()
                    return render_template("profil.html") 
                else:
                    flash('Some Ting WONG')
            else:
                flash('Din lösenord matchar ej, pröva igen')
        else:
            return render_template("newpasswd.html")
    else:
        return redirect(url_for("login"))
      
    

#Bara den som startar, detta gör det möjligt för WSGI ska fungera.. den letar efter vår flask applikation.
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=43210, debug=True)



