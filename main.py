import os
import re
import json
import time
import shlex

from tkinter import *
from tkinter import ttk
from tkinter import filedialog
from tkinter import messagebox

import tiktoken
import tkinter as tk

from utils import docker, write_config
from openai import OpenAI
from datetime import datetime
from functools import partial

import threading
import traceback


active_containers = []


def on_close():
    for container in active_containers:
        os.system(f"docker stop -t 0 {container}")
    root.destroy()


root = Tk()
root.protocol("WM_DELETE_WINDOW", on_close)
selected_video = StringVar()
progressbar = ttk.Progressbar(length=400)
root.title("Script cleaner")
frm = ttk.Frame(root, padding=10)
frm.grid(column=0, row=0)
solution = "You can solve this problem by increasing 'Percent of LLM context to use for response'"

layout = {
    'label_over_select_button': {
        'column': 0,
        'row': 0
    },
    'select_button': {
        'column': 0,
        'row': 1,
        'pady': 10
    },
    'text_area': {
        'column': 0,
        'row': 2,
        'pady': 10
    },
    'use_existing_files_checkbox': {
        'column': 0,
        'row': 3,
        'sticky': "w"
    },
    'max_tokens_label': {
        'column': 0,
        'row': 4,
        'sticky': "w"
    },
    'max_tokens': {
        'column': 0,
        'row': 4,
        'sticky': "e"
    },
    'percent_of_max_tokens_to_use_for_response_label': {
        'column': 0,
        'row': 5,
        'sticky': "w"
    },
    'percent_of_max_tokens_to_use_for_response': {
        'column': 0,
        'row': 5,
        'sticky': "w",
        'padx': (400, 0)
    },
    'current_activity_message': {
        'column': 0,
        'row': 6
    },
    'progressbar': {
        'column': 0,
        'row': 7
    },
    'run_button': {
        'column': 0,
        'row': 8
    },
    'done_message': {
        'column': 0,
        'row': 10
    },
    'notify_message': {
        'column': 0,
        'row': 12
    },
    'button_under_notify_message': {
        'column': 0,
        'row': 11
    },
}

ttk.Label(frm, text="Video isn't selected").grid(**layout['label_over_select_button'])

label = 'Select video'
current_directory = os.path.dirname(os.path.abspath(__file__))
threads = {}
use_existing_files = BooleanVar()
use_existing_files.set(True)
Checkbutton(
    frm,
    text='Use existing files',
    variable=use_existing_files
).grid(**layout['use_existing_files_checkbox'])


def get_text_only(path):
    #path = '/home/nikos/sample.txt'

    tmp, ext = os.path.splitext(path)
    folder = os.path.dirname(tmp)
    filename = os.path.basename(tmp)
    with open(path, 'r') as f:
        text = f.read()
    result = re.split(r'\[[\d:.]+\s*-->\s*[\d:.]+\]', text)
    result = ''.join(result)
    for item in ['[MUSIC]', '[BLANK_AUDIO]', '>>', '\n']:
        result = result.replace(item, '')
    result = result.strip()
    result = re.sub(r'\s+', ' ', result)

    now = datetime.now()
    formatted_datetime = now.strftime("%Y_%m_%d_%H_%M_%S")
    out_file = os.path.join(folder, filename + '_out_' + formatted_datetime + ext)
    path = os.path.join(folder, filename + '_text_only' + ext)
    with open(path, 'w') as f:
        f.write(result)
    return result, out_file


def load_config():
    with open(os.path.join(current_directory, 'config.json'), 'r') as f:
        return json.loads(f.read())


def call_chatgpt(config, model, client, system_message, user_mesage, out_file, tokens_for_response):
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": system_message
            },
            {
                "role": "user",
                "content": user_mesage
            }
        ],
        temperature=config['temperature'],
        max_tokens=tokens_for_response,  # desired response size
        top_p=config['top_p'],
        frequency_penalty=config['frequency_penalty'],
        presence_penalty=config['presence_penalty']
    )
    while response.choices[0].finish_reason == 'null':
        time.sleep(1)

    if response.choices[0].finish_reason == 'length':
        notify("finish_reason == 'length'\n" + solution)
        return True

    if response.choices[0].finish_reason == 'stop':
        out = response.choices[0].message.content
    else:
        out = f"\n\n\nUnusual finish_reason = '{response.choices[0].finish_reason}' for Reqest:\n {system_message}\n\n{user_mesage}\n\nResponse:{response.choices[0].message.content}\n\n\n"
    with open(out_file, 'a') as f:
        f.write(out)
    return False


def clear(slug):
    for slave in frm.grid_slaves(row=layout[slug]['row'], column=layout[slug]['column']):
        slave.destroy()


def try_split(delimiter, text, tokens_for_request, encoding, config):
    sentences = text.split(delimiter)
    offset = 0
    input_tokens = 0
    out_tokens = 0
    request_is_too_big = False
    while offset < len(sentences):
        request = []
        while offset < len(sentences):
            sentence = sentences[offset]
            tmp = delimiter.join(request + [config['prompt'], sentence])
            cnt = len(encoding.encode(tmp))
            if cnt <= tokens_for_request:
                request.append(sentence)
                offset += 1
            else:
                break

        if not request and offset < len(sentences):
            request_is_too_big = True
            break

        request = delimiter.join(request)
        request_input_tokens = len(encoding.encode(request + config['prompt']))
        input_tokens += request_input_tokens
        out_tokens += (8192 - request_input_tokens - 100)
    return request_is_too_big, input_tokens, out_tokens


def estimate_cost(text, tokens_for_request, encoding, config):
    point_attempt = try_split('.', text, tokens_for_request, encoding, config)
    space_attempt = try_split(' ', text, tokens_for_request, encoding, config)
    if (not point_attempt[0]) or (not space_attempt[0]):
        if not point_attempt[0]:
            choice = point_attempt
            delimeter = '.'
        elif not space_attempt[0]:
            choice = space_attempt
            delimeter = ' '
        input_tokens = choice[1]
        out_tokens = choice[2]
        cost = round(((input_tokens / 1000) * 0.03) + ((out_tokens / 1000) * 0.06), 1)
        accepted = messagebox.askyesno("Cost estimation", f"Processing by ChatGPT will use \n{input_tokens} input tokens\n{out_tokens} output tokens\ntotal cost approximately {cost} $\n\nDou you want to continue?")
        return accepted, delimeter
    else:
        notify(f"Can't create request for an sentence. The sentence is too big.\n" +
               "You may solve this problem by reducing 'Percent of LLM context to use for response'. If it doesn't help then mail to nicksheuko@gmail.com")
        return False, None


def send_to_chatgpt(txt_file_path, progressbar):
    text, out_file = get_text_only(txt_file_path)

    model = "gpt-4"
    config = load_config()
    encoding = tiktoken.encoding_for_model(model)
    tokens_for_request_and_response = 8192
    p = config['percent_of_max_tokens_to_use_for_response'] / 100
    tokens_for_request = int(tokens_for_request_and_response * (1 - p))

    feed, delimeter = estimate_cost(text, tokens_for_request, encoding, config)
    if not feed:
        clear('done_message')
        return

    client = OpenAI(api_key=config['chatgpt_api_key'])
    offset = 0
    sentences = text.split(delimeter)
    #sentences = sentences[0:2]
    clear('done_message')
    ttk.Label(frm, text=f"You can observe progress in file {out_file}").grid(
        **layout['done_message']
    )
    stop = False
    progressbar['value'] = 0
    while offset < len(sentences):
        request = []
        while offset < len(sentences):
            sentence = sentences[offset]
            tmp = delimeter.join(request + [config['prompt'], sentence])
            cnt = len(encoding.encode(tmp))
            if cnt <= tokens_for_request:
                request.append(sentence)
                offset += 1
            else:
                break

        request = delimeter.join(request)
        tokens_for_response = tokens_for_request_and_response - len(encoding.encode(request + config['prompt'])) - 100
        stop = call_chatgpt(config, model, client, config['prompt'], request, out_file, tokens_for_response)
        progressbar['value'] = ((offset + 1) / len(sentences)) * 100
        if stop:
            break
    if stop:
        msg = f"Not complete result in file {out_file}\n{solution}"
    else:
        msg = f"Done. Result in file {out_file}"

    clear('done_message')
    ttk.Label(frm, text=msg).grid(**layout['done_message'])


def copy_message(text_to_copy):
    root.clipboard_clear()
    root.clipboard_append(text_to_copy)
    root.update()


def notify(message):
    clear('notify_message')
    ttk.Label(frm, text=message).grid(**layout['notify_message'])
    clear('button_under_notify_message')
    ttk.Button(frm, text='Copy message above', command=partial(copy_message, message)).grid(
        **layout['button_under_notify_message']
    )


def run2(video, progressbar, use_existing_files):
    try:
        folder_path, file_name = os.path.split(video)
        base_name, _ = os.path.splitext(file_name)
        wav_exists = os.path.exists(os.path.join(folder_path, base_name + '.wav'))
        if not wav_exists or not use_existing_files:
            input_file = os.path.join('/videos', shlex.quote(file_name))
            out_file = os.path.join('/videos', shlex.quote(base_name + '.wav'))
            label = ttk.Label(frm, text="Extracting audio")
            label.grid(**layout['current_activity_message'])
            progressbar['value'] = 5
            active_containers.append('ffmpeg')
            response = docker(
                [(shlex.quote(folder_path), '/videos')],
                f"ffmpeg -i {input_file} -ar 16000 -ac 1 -c:a pcm_s16le -y {out_file}",
                'ffmpeg'
            )
            active_containers.remove('ffmpeg')
            label.grid_remove()
            if response != 0:
                notify("Audio extraction failed")
                return

        progressbar['value'] = 10

        txt_file_path = os.path.join(folder_path, base_name + '.txt')
        txt_exists = os.path.exists(txt_file_path)
        if not txt_exists or not use_existing_files:
            label = ttk.Label(frm, text="Extracting text from audio")
            label.grid(**layout['current_activity_message'])
            active_containers.append('whisper')
            response = docker(
                [(shlex.quote(folder_path), '/videos'), (shlex.quote(current_directory), '/models')],
                f"./main -m /models/ggml-base.en.bin -t {os.cpu_count() - 1} -f /videos/{shlex.quote(base_name)}.wav > /videos/{shlex.quote(base_name)}.txt",
                'whisper'
            )
            active_containers.remove('whisper')
            label.grid_remove()
            if response != 0:
                notify("Extracting text from audio failed")
                return
        progressbar['value'] = 50
        label = ttk.Label(frm, text="Feeding ChatGPT with extracted text")
        label.grid(**layout['current_activity_message'])
        send_to_chatgpt(txt_file_path, progressbar)
        label.grid_remove()
    except Exception as e:
        notify(str(e) + '\n' + traceback.format_exc())


def run():
    video = selected_video.get()
    if not video:
        messagebox.showinfo(
            "Error",
            "Select video file first"
        )
        return

    clear('done_message')
    clear('button_under_notify_message')
    clear('current_activity_message')

    progressbar.grid(**layout['progressbar'])
    run_button.config(state=tk.DISABLED)

    folder_path, file_name = os.path.split(video)
    base_name, _ = os.path.splitext(file_name)
    t = threading.Thread(
        target=run2,
        args=(video, progressbar, use_existing_files.get()),
        daemon=True
    )
    t.start()
    threads[t.ident] = t


def select_video():
    file_path = filedialog.askopenfilename(title=label)
    if file_path:
        selected_video.set(file_path)
        ttk.Label(frm, text=f"Selected video: {file_path}").grid(**layout['label_over_select_button'])


def enable_run_button_remove_progress():
    progressbar.stop()
    progressbar.grid_remove()
    run_button.config(state=tk.NORMAL)


def threads_watcher():
    for id in list(threads.keys()):
        thread = threads[id]
        if not thread.is_alive():
            enable_run_button_remove_progress()
            del threads[id]

    root.after(500, threads_watcher)


def on_text_change(event):
    text_area.edit_modified(False)
    config = load_config()
    config['prompt'] = text_area.get("1.0", tk.END).strip()
    write_config(config)


def select_all(event):
    text_area.tag_add(tk.SEL, "1.0", tk.END)
    text_area.mark_set(tk.INSERT, tk.END)
    text_area.see(tk.INSERT)
    return 'break'


ttk.Button(frm, text=label, command=select_video).grid(**layout['select_button'])
text_area = tk.Text(frm, height=10, width=70)
text_area.grid(**layout['text_area'])
text_area.insert(tk.END, load_config()['prompt'])
text_area.bind("<<Modified>>", on_text_change)
text_area.bind('<Control-a>', select_all)
text_area.bind('<Control-A>', select_all)


percent_of_max_tokens_to_use_for_response_var = tk.StringVar()


def on_percent_of_max_tokens_to_use_for_response_change(*args):
    config = load_config()
    config['percent_of_max_tokens_to_use_for_response'] = int(percent_of_max_tokens_to_use_for_response_var.get())
    write_config(config)


ttk.Label(frm, text="Percent of LLM context to use for response").grid(
    **layout['percent_of_max_tokens_to_use_for_response_label']
)

percent_of_max_tokens_to_use_for_response_var.trace("w", on_percent_of_max_tokens_to_use_for_response_change)
percent_of_max_tokens_to_use_for_response = Entry(frm, width=10, textvariable=percent_of_max_tokens_to_use_for_response_var)
percent_of_max_tokens_to_use_for_response.grid(**layout['percent_of_max_tokens_to_use_for_response'])
percent_of_max_tokens_to_use_for_response.insert(0, str(load_config()['percent_of_max_tokens_to_use_for_response']))


run_button = ttk.Button(frm, text='Run', command=run)
run_button.grid(**layout['run_button'])
threads_watcher()
root.mainloop()






