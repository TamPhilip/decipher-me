from flask import Flask, Response, request, render_template, jsonify
import smooch
from smooch.rest import ApiException
from google.cloud import translate_v2 as translate
import six
import os
import time


os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "./path/to/file"
smooch.configuration.username = 'app_id'
smooch.configuration.password = 'app_secret'
app_id = "integration_id"

# App
translate_client = translate.Client()
app = Flask(__name__)
api_instance = smooch.ConversationApi()


class Store:
    storage = {}

    user_id_timestamp = {}
    conversations = {}
    discussing_to = {}

    waiting = {}
    translating = {}
    language = {}

    ids = []


def create_conversation(user_id):
    Store.waiting[user_id] = True
    ts = str(int(time.time()))
    Store.conversations[ts] = {"users": [user_id]}
    post_messages("Room was created with ID: {}".format(ts), user_id)
    Store.user_id_timestamp[user_id] = ts
    post_messages('''Ask user to join with "cmd join {}".'''.format(ts), user_id)

def create_conversation_alone(user_id):
    ts = str(int(time.time()))
    Store.conversations[ts] = {"users": [user_id]}
    Store.user_id_timestamp[user_id] = ts
    Store.conversations[ts]["users"].append(user_id)
    Store.translating[user_id] = True
    Store.waiting[user_id] = False
    Store.discussing_to[user_id] = user_id
    Store.user_id_timestamp[user_id] = ts
    post_messages("Self study mode activated! Start writing sentences and it will be sent back to you in your translated language:", user_id=user_id)

def get_languages(user_id):
    results = translate_client.get_languages()
    for language in results:
        post_messages(u'{name} ({language})'.format(**language), user_id=user_id)

def join_conversation(user_id, time_stamp):
    if time_stamp in Store.conversations:
        post_messages("Conversation does not exist", user_id)
    elif Store.conversations[time_stamp]["users"][0] == user_id:
        post_messages("Cannot join own conversation!", user_id)
    else:
        Store.conversations[time_stamp]["users"].append(user_id)
        user_ids = Store.conversations[time_stamp]["users"]
        for user in user_ids:
            Store.translating[user] = True
            Store.waiting[user] = False
        Store.discussing_to[user_ids[0]] = user_ids[1]
        Store.discussing_to[user_ids[1]] = user_ids[0]
        ts = Store.user_id_timestamp[user_ids[0]]
        Store.user_id_timestamp[user_ids[1]] = ts
        post_messages("Joined conversation successfully", user_ids[0])
        post_messages("Joined conversation successfully", user_ids[1])

def translate_text(text, user_id):
    if isinstance(text, six.binary_type):
        text = text.decode('utf-8')

    # Text can also be a sequence of strings, in which case this method
    # will return a sequence of results for each text.
    result = translate_client.translate(
        text, target_language=Store.conversations[Store.language[Store.discussing_to[user_id]]], mime_type='text/plain')

    print(u'Text: {}'.format(result['input']))
    print(u'Translation: {}'.format(result['translatedText']))
    print(u'Detected source language: {}'.format(result['detectedSourceLanguage']))

    return result['translatedText']


def post_messages(message, user_id):
    try:
        message_post_body = smooch.MessagePost(role="appMaker", text=message, type="text")
        api_response = api_instance.post_message(app_id, user_id, message_post_body)
        return api_response
    except ApiException as e:
        print("Exception when calling AppApi->create_app: %s\n" % e)


def post_start(user_id):
    post_messages("Welcome to DecipherMe \n We are a translation application that offers commands! ", user_id)
    post_commands(user_id)


def post_commands(user_id):
    post_messages("Here is the list of commands", user_id)
    time.sleep(1)
    post_messages('''"cmd start" - creates a room''', user_id)
    post_messages('''"cmd start_alone" - enter translation mode alone ''', user_id)
    post_messages('''"cmd exit" - exit translation mode''', user_id)
    post_messages('''"cmd set {lang}" - sets the language to the specified language''', user_id)
    post_messages('''"cmd cmds" - display all commands''', user_id)
    post_messages('''"cmd languages" - display all languages''', user_id)
    post_messages('''"cmd join {ID}" - join the room of players''', user_id)


def post_end(user_id):
    post_messages("Thank you for using our services!", user_id)


def post_argument_missing(user_id):
    post_messages("Failed to execute command because arguments are missing.", user_id)


def post_left_the_room(user_id, user_left=False):
    if user_left:
        post_messages("The other user has left.")
    post_messages("The conversation has ended. \n Thank you for trying the app!", user_id)


def handle_commands(cmd, user_id):
    c = cmd.split()
    if len(c) == 1:
        post_argument_missing(user_id)
        return
    if c[1] == "start":
        if Store.waiting[user_id]:
            post_messages("Cannot create another room while waiting.", user_id)
            return
        create_conversation(user_id)
    elif c[1] == "start_alone":
        create_conversation_alone(user_id)
    elif c[1] == "languages":
        get_languages()
    elif c[1] == "cmds":
        post_commands(user_id)
    elif c[1] == "set":
        if len(c) < 2:
            post_argument_missing(user_id)
            return
        Store.language[user_id] = c[2]
        post_messages("Set languages to {}, this will be the language you will be receiving messages".format(c[2]), user_id)
    elif c[1] == "exit":
        if user_id in Store.discussing_to:
            ts = Store.user_id_timestamp[user_id]
            Store.conversations[ts] = None
            user_id_2 = Store.discussing_to[user_id]
            Store.discussing_to[user_id_2] = None
            Store.discussing_to[user_id] = None
            Store.translating[user_id] = False
            Store.translating[user_id_2] = False
            if user_id != user_id_2:
                post_left_the_room(user_id_2, True)
                post_end(user_id_2)
            post_end(user_id)
        else:
            if Store.waiting[user_id]:
                Store.waiting[user_id] = False
                ts = Store.user_id_timestamp[user_id]
                Store.conversations[ts] = None
                Store.user_id_timestamp[user_id] = None
                post_messages("You have successfully left the room.", user_id)
    elif c[1] == "join":
        if len(c) < 2:
            post_argument_missing(user_id)
            return
        join_conversation(user_id, c[2])
    else:
        post_messages("Command is invalid.", user_id)
        post_commands(user_id)


#  Renders the main root
@app.route('/', methods = ['GET'])
def main():
    return '''DDDDDDDDDDDDD      EEEEEEEEEEEEEEEEEEEEEE       CCCCCCCCCCCCCIIIIIIIIIIPPPPPPPPPPPPPPPPP   HHHHHHHHH     HHHHHHHHHEEEEEEEEEEEEEEEEEEEEEERRRRRRRRRRRRRRRRR                    MMMMMMMM               MMMMMMMMEEEEEEEEEEEEEEEEEEEEEE \nD::::::::::::DDD   E::::::::::::::::::::E    CCC::::::::::::CI::::::::IP::::::::::::::::P  H:::::::H     H:::::::HE::::::::::::::::::::ER::::::::::::::::R                   M:::::::M             M:::::::ME::::::::::::::::::::E\nD:::::::::::::::DD E::::::::::::::::::::E  CC:::::::::::::::CI::::::::IP::::::PPPPPP:::::P H:::::::H     H:::::::HE::::::::::::::::::::ER::::::RRRRRR:::::R                  M::::::::M           M::::::::ME::::::::::::::::::::E\nDDD:::::DDDDD:::::DEE::::::EEEEEEEEE::::E C:::::CCCCCCCC::::CII::::::IIPP:::::P     P:::::PHH::::::H     H::::::HHEE::::::EEEEEEEEE::::ERR:::::R     R:::::R                 M:::::::::M         M:::::::::MEE::::::EEEEEEEEE::::E\nD:::::D    D:::::D E:::::E       EEEEEEC:::::C       CCCCCC  I::::I    P::::P     P:::::P  H:::::H     H:::::H    E:::::E       EEEEEE  R::::R     R:::::R                 M::::::::::M       M::::::::::M  E:::::E       EEEEEE\nD:::::D     D:::::DE:::::E            C:::::C                I::::I    P::::P     P:::::P  H:::::H     H:::::H    E:::::E               R::::R     R:::::R                 M:::::::::::M     M:::::::::::M  E:::::E             \nD:::::D     D:::::DE::::::EEEEEEEEEE  C:::::C                I::::I    P::::PPPPPP:::::P   H::::::HHHHH::::::H    E::::::EEEEEEEEEE     R::::RRRRRR:::::R                  M:::::::M::::M   M::::M:::::::M  E::::::EEEEEEEEEE   \nD:::::D     D:::::DE:::::::::::::::E  C:::::C                I::::I    P:::::::::::::PP    H:::::::::::::::::H    E:::::::::::::::E     R:::::::::::::RR   --------------- M::::::M M::::M M::::M M::::::M  E:::::::::::::::E   \nD:::::D     D:::::DE:::::::::::::::E  C:::::C                I::::I    P::::PPPPPPPPP      H:::::::::::::::::H    E:::::::::::::::E     R::::RRRRRR:::::R  -:::::::::::::- M::::::M  M::::M::::M  M::::::M  E:::::::::::::::E   \nD:::::D     D:::::DE::::::EEEEEEEEEE  C:::::C                I::::I    P::::P              H::::::HHHHH::::::H    E::::::EEEEEEEEEE     R::::R     R:::::R --------------- M::::::M   M:::::::M   M::::::M  E::::::EEEEEEEEEE   \nD:::::D     D:::::DE:::::E            C:::::C                I::::I    P::::P              H:::::H     H:::::H    E:::::E               R::::R     R:::::R                 M::::::M    M:::::M    M::::::M  E:::::E             \nD:::::D    D:::::D E:::::E       EEEEEEC:::::C       CCCCCC  I::::I    P::::P              H:::::H     H:::::H    E:::::E       EEEEEE  R::::R     R:::::R                 M::::::M     MMMMM     M::::::M  E:::::E       EEEEEE\nDDD:::::DDDDD:::::DEE::::::EEEEEEEE:::::E C:::::CCCCCCCC::::CII::::::IIPP::::::PP          HH::::::H     H::::::HHEE::::::EEEEEEEE:::::ERR:::::R     R:::::R                 M::::::M               M::::::MEE::::::EEEEEEEE:::::E\nD:::::::::::::::DD E::::::::::::::::::::E  CC:::::::::::::::CI::::::::IP::::::::P          H:::::::H     H:::::::HE::::::::::::::::::::ER::::::R     R:::::R                 M::::::M               M::::::ME::::::::::::::::::::E\nD::::::::::::DDD   E::::::::::::::::::::E    CCC::::::::::::CI::::::::IP::::::::P          H:::::::H     H:::::::HE::::::::::::::::::::ER::::::R     R:::::R                 M::::::M               M::::::ME::::::::::::::::::::E\nDDDDDDDDDDDDD      EEEEEEEEEEEEEEEEEEEEEE       CCCCCCCCCCCCCIIIIIIIIIIPPPPPPPPPP          HHHHHHHHH     HHHHHHHHHEEEEEEEEEEEEEEEEEEEEEERRRRRRRR     RRRRRRR                 MMMMMMMM               MMMMMMMMEEEEEEEEEEEEEEEEEEEEEE'''


@app.route('/messages', methods=['POST'])
def messages():
    content = request.get_json()
    print(content['messages'][0]['text'])
    user_id = content["appUser"]["_id"]

    # New users are created
    if user_id not in Store.ids:
        Store.ids.append(user_id)
        Store.storage[user_id] = []
        Store.waiting[user_id] = False
        Store.translating[user_id] = False
        Store.language[user_id] = "eng"

    # This is command
    if content['messages'][0]['text'].split()[0] == "cmd":
        handle_commands(content['messages'][0]['text'], user_id)
        message = {
            'status': 200,
            'message': 'OK',
            'cmd': content['messages'][0]['text']
        }
        to_return = jsonify(message)
        to_return.status_code = 200
        return to_return

    # If they are not waiting and translating
    if Store.translating[user_id]:
        res = post_messages(translate_text(content['messages'][0]['text'], user_id), Store.discussing_to[user_id])
        Store.storage[user_id].append(res)
        message = {
            'status': 200,
            'message': 'OK',
        }
        to_return = jsonify(message)
        to_return.status_code = 200
        return to_return

    # If they are waiting
    if Store.waiting[user_id] is True:
        post_messages('''Please wait patiently or use the "cmd exit" to leave room.''', user_id)
        message = {
            'status': 200,
            'message': 'OK',
        }
        to_return = jsonify(message)
        to_return.status_code = 200
        return to_return

    # Just started
    post_start(user_id)
    message = {
        'status': 200,
        'message': 'OK'
    }
    to_return = jsonify(message)
    to_return.status_code = 200
    return to_return


if __name__ == "__main__":
    app.run()
