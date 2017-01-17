from xbmcswift2 import Plugin
from xbmcswift2 import actions
import xbmc,xbmcaddon,xbmcvfs,xbmcgui
import re
from rpc import RPC
import requests
import random
import sqlite3
#from datetime import datetime,timedelta
import datetime
import time
#import urllib
import HTMLParser
import xbmcplugin
#import xml.etree.ElementTree as ET
#import sqlite3
import os
#import shutil
#from rpc import RPC
from types import *
import json

plugin = Plugin()
big_list_view = False

def log2(v):
    xbmc.log(repr(v))

def log(v):
    xbmc.log(re.sub(',',',\n',repr(v)))

def get_icon_path(icon_name):
    addon_path = xbmcaddon.Addon().getAddonInfo("path")
    return os.path.join(addon_path, 'resources', 'img', icon_name+".png")


def remove_formatting(label):
    label = re.sub(r"\[/?[BI]\]",'',label)
    label = re.sub(r"\[/?COLOR.*?\]",'',label)
    return label

@plugin.route('/addon/<id>')
def addon(id):
    addon = plugin.get_storage(id)
    items = []
    for name in sorted(addon):
        url = addon[name]
        items.append(
        {
            'label': name,
            'path': url,
            'thumbnail':get_icon_path('tv'),
            'is_playable':True,
        })
    return items

@plugin.route('/player')
def player():
    if not plugin.get_setting('addons.folder'):
        dialog = xbmcgui.Dialog()
        dialog.notification("addons.ini Creator", "Set Folder",xbmcgui.NOTIFICATION_ERROR )
        xbmcaddon.Addon ('plugin.video.addons.ini.creator').openSettings()

    addons = plugin.get_storage("addons")
    for a in addons.keys():
        add = plugin.get_storage(a)
        add.clear()
    addons.clear()

    folder = plugin.get_setting("addons.folder")
    file = plugin.get_setting("addons.file")
    filename = os.path.join(folder,file)
    f = xbmcvfs.File(filename,"rb")
    lines = f.read().splitlines()

    addon = None
    for line in lines:
        if line.startswith('['):
            a = line.strip('[]')
            addons[a] = a
            addon = plugin.get_storage(a)
            addon.clear()
        elif "=" in line:
            (name,url) = line.split('=',1)
            if url and addon is not None:
                addon[name] = url

    items = []
    for id in sorted(addons):
        items.append(
        {
            'label': id,
            'path': plugin.url_for('addon',id=id),
            'thumbnail':get_icon_path('tv'),
        })
    return items

@plugin.route('/play/<url>')
def play(url):
    xbmc.executebuiltin('PlayMedia(%s)' % url)

@plugin.route('/pvr_subscribe')
def pvr_subscribe():
    plugin.set_setting("pvr.subscribe","true")
    xbmc.executebuiltin('Container.Refresh')

@plugin.route('/pvr_unsubscribe')
def pvr_unsubscribe():
    plugin.set_setting("pvr.subscribe","false")
    xbmc.executebuiltin('Container.Refresh')

@plugin.route('/add_folder/<id>/<path>')
def add_folder(id,path):
    folders = plugin.get_storage('folders')
    folders[path] = id
    xbmc.executebuiltin('Container.Refresh')

@plugin.route('/remove_folder/<id>/<path>')
def remove_folder(id,path):
    folders = plugin.get_storage('folders')
    del folders[path]
    xbmc.executebuiltin('Container.Refresh')

@plugin.route('/clear_cache')
def clear_cache():
    last_read = plugin.get_storage('last_read')
    last_read.clear()
    xbmcvfs.delete('special://profile/addon_data/plugin.video.stream.searcher/cache.json')

@plugin.route('/clear')
def clear():
    folders = plugin.get_storage('folders')
    folders.clear()

@plugin.route('/add_channel')
def add_channel():
    channels = plugin.get_storage('channels')
    d = xbmcgui.Dialog()
    channel = d.input("Add Channel")
    if channel:
        channels[channel] = ""
    xbmc.executebuiltin('Container.Refresh')


@plugin.route('/remove_channel')
def remove_channel():
    channels = plugin.get_storage('channels')
    channel_list = sorted(channels)
    d = xbmcgui.Dialog()
    which = d.select("Remove Channel",channel_list)
    if which == -1:
        return
    channel = channel_list[which]
    del channels[channel]
    xbmc.executebuiltin('Container.Refresh')

@plugin.route('/remove_this_channel/<channel>')
def remove_this_channel(channel):
    channels = plugin.get_storage('channels')
    del channels[channel]
    xbmc.executebuiltin('Container.Refresh')

@plugin.route('/clear_channels')
def clear_channels():
    channels = plugin.get_storage('channels')
    channels.clear()
    xbmc.executebuiltin('Container.Refresh')

@plugin.route('/import_channels')
def import_channels():
    channels = plugin.get_storage('channels')
    d = xbmcgui.Dialog()
    filename = d.browse(1, 'Import Channels', 'files', '', False, False, 'special://home/')
    if not filename:
        return
    if filename.endswith('.ini'):
        lines = xbmcvfs.File(filename,'rb').read().splitlines()
        for line in lines:
            if not line.startswith('[') and not line.startswith('#') and "=" in line:
                channel_url = line.split('=',1)
                if len(channel_url) == 2:
                    name = channel_url[0]
                    channels[name] = ""
    xbmc.executebuiltin('Container.Refresh')

@plugin.route('/export_channels')
def export_channels():
    channels = plugin.get_storage('channels')

    f = xbmcvfs.File('special://profile/addon_data/plugin.video.stream.searcher/stream_searcher_export.ini','wb')
    for channel in sorted(channels):
        url = plugin.url_for('stream_search',channel=channel)
        s = "%s=%s\n" % (channel,url)
        f.write(s)
    f.close()


@plugin.route('/folder/<id>/<path>')
def folder(id,path):
    folders = plugin.get_storage('folders')
    try: response = RPC.files.get_directory(media="files", directory=path, properties=["thumbnail"])
    except: return
    files = response["files"]
    dirs = dict([[remove_formatting(f["label"]), f["file"]] for f in files if f["filetype"] == "directory"])
    links = {}
    thumbnails = {}
    for f in files:
        if f["filetype"] == "file":
            label = remove_formatting(f["label"])
            file = f["file"]
            while (label in links):
                label = "%s." % label
            links[label] = file
            thumbnails[label] = f["thumbnail"]

    items = []

    for label in sorted(dirs):
        folder_path = dirs[label]
        context_items = []
        if path in folders:
            fancy_label = "[COLOR yellow][B]%s[/B][/COLOR] " % label
            context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Remove Folder', 'XBMC.RunPlugin(%s)' % (plugin.url_for(remove_folder, id=id, path=folder_path))))
        else:
            fancy_label = "[B]%s[/B]" % label
            context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Add Folder', 'XBMC.RunPlugin(%s)' % (plugin.url_for(add_folder, id=id, path=folder_path))))
        items.append(
        {
            'label': fancy_label,
            'path': plugin.url_for('folder',id=id, path=folder_path),
            'thumbnail': get_icon_path('tv'),
            'context_menu': context_items,
        })

    for label in sorted(links):
        items.append(
        {
            'label': label,
            'path': plugin.url_for('play',url=links[label]),
            'thumbnail': thumbnails[label],
        })
    return items

@plugin.route('/pvr')
def pvr():
    index = 0
    urls = []
    channels = {}
    for group in ["radio","tv"]:
        urls = urls + xbmcvfs.listdir("pvr://channels/%s/All channels/" % group)[1]
    for group in ["radio","tv"]:
        groupid = "all%s" % group
        try: json_query = RPC.PVR.get_channels(channelgroupid=groupid, properties=[ "thumbnail", "channeltype", "hidden", "locked", "channel", "lastplayed", "broadcastnow" ] )
        except: continue
        if "channels" in json_query:
            for channel in json_query["channels"]:
                channelname = channel["label"]
                channelid = channel["channelid"]-1
                channellogo = channel['thumbnail']
                streamUrl = urls[index]
                index = index + 1
                url = "pvr://channels/%s/All channels/%s" % (group,streamUrl)
                channels[url] = channelname
    items = []
    for url in sorted(channels, key=lambda x: channels[x]):
        name = channels[url]
        items.append(
        {
            'label': name,
            'path': url,
            'is_playable': True,
        })
    return items

@plugin.route('/subscribe')
def subscribe():
    folders = plugin.get_storage('folders')
    ids = {}
    for folder in folders:
        id = folders[folder]
        ids[id] = id
    all_addons = []
    for type in ["xbmc.addon.video", "xbmc.addon.audio"]:
        try: response = RPC.addons.get_addons(type=type,properties=["name", "thumbnail"])
        except: continue
        if "addons" in response:
            found_addons = response["addons"]
            all_addons = all_addons + found_addons

    seen = set()
    addons = []
    for addon in all_addons:
        if addon['addonid'] not in seen:
            addons.append(addon)
        seen.add(addon['addonid'])

    items = []

    pvr = plugin.get_setting('pvr.subscribe')
    context_items = []
    label = "PVR"
    if pvr == "true":
        fancy_label = "[COLOR yellow][B]%s[/B][/COLOR] " % label
        context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Remove Folder', 'XBMC.RunPlugin(%s)' % (plugin.url_for(pvr_unsubscribe))))
    else:
        fancy_label = "[B]%s[/B]" % label
        context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Add Folder', 'XBMC.RunPlugin(%s)' % (plugin.url_for(pvr_subscribe))))
    items.append(
    {
        'label': fancy_label,
        'path': plugin.url_for('pvr'),
        'thumbnail':get_icon_path('tv'),
        'context_menu': context_items,
    })

    addons = sorted(addons, key=lambda addon: remove_formatting(addon['name']).lower())
    for addon in addons:
        label = remove_formatting(addon['name'])
        id = addon['addonid']
        path = "plugin://%s" % id
        context_items = []
        if id in ids:
            fancy_label = "[COLOR yellow][B]%s[/B][/COLOR] " % label
            context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Remove Folder', 'XBMC.RunPlugin(%s)' % (plugin.url_for(remove_folder, id=id, path=path))))
        else:
            fancy_label = "[B]%s[/B]" % label
            context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Add Folder', 'XBMC.RunPlugin(%s)' % (plugin.url_for(add_folder, id=id, path=path))))
        items.append(
        {
            'label': fancy_label,
            'path': plugin.url_for('folder',id=id, path=path),
            'thumbnail': get_icon_path('tv'),
            'context_menu': context_items,
        })
    return items



@plugin.route('/stream_search/<channel>')
def stream_search(channel):
    file_name = 'special://profile/addon_data/plugin.video.stream.searcher/cache.json'
    folders = plugin.get_storage('folders')
    last_read = plugin.get_storage('last_read')
    streams = {}
    f = xbmcvfs.File(file_name,'rb')
    data = f.read()
    f.close()
    if data:
        streams = json.loads(data)

    for folder in folders:
        path = folder
        id = folders[folder]
        now = datetime.datetime.now()
        last_time = last_read.get(folder)
        if last_time:
            format = "%Y-%m-%dT%H:%M:%S.%f"
            try:
                last_time = datetime.datetime.strptime(last_time, format)
            except TypeError:
                last_time = datetime.datetime(*(time.strptime(last_time, format)[0:6]))
            hours = int(plugin.get_setting('cache.hours'))
            if last_time > now - datetime.timedelta(hours=hours):
                continue
        last_read[folder] = now.isoformat()

        if not id in streams:
            streams[id] = {}
        try: response = RPC.files.get_directory(media="files", directory=path)
        except: continue
        if not 'error' in response:
            if 'files' not in response:
                continue
            files = response["files"]
            for f in files:
                if f["filetype"] == "file":
                    label = remove_formatting(f["label"])
                    file = f["file"]
                    streams[id][file] = label


    f = xbmcvfs.File(file_name,'wb')
    data = json.dumps(streams,indent=2)
    f.write(data)
    f.close()

    channel_search = channel.decode("utf8").lower().replace(' ','')
    stream_list = []
    for id in sorted(streams):
        files = streams[id]
        for f in sorted(files, key=lambda k: files[k]):
            label = files[f]
            label_search = label.decode("utf8").lower().replace(' ','')
            if label_search in channel_search or channel_search in label_search:
                stream_list.append((id,f,label))
    labels = ["[%s] %s" % (x[0],x[2]) for x in stream_list]
    d = xbmcgui.Dialog()
    which = d.select(channel, labels)
    if which == -1:
        return
    stream_name = stream_list[which][2]
    stream_link = stream_list[which][1]
    plugin.set_resolved_url(stream_link)

@plugin.route('/channel_player')
def channel_player():
    channels = plugin.get_storage("channels")

    items = []
    for channel in sorted(channels):
        context_items = []
        context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Add Channel', 'XBMC.RunPlugin(%s)' % (plugin.url_for(add_channel))))
        context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Remove Channel', 'XBMC.RunPlugin(%s)' % (plugin.url_for(remove_this_channel, channel=channel))))
        context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Import Channels', 'XBMC.RunPlugin(%s)' % (plugin.url_for(import_channels))))
        context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Clear Channels', 'XBMC.RunPlugin(%s)' % (plugin.url_for(clear_channels))))
        items.append(
        {
            'label': channel,
            'path': plugin.url_for('stream_search',channel=channel),
            'thumbnail':get_icon_path('tv'),
            'is_playable': True,
            'context_menu': context_items,
        })
    return items

@plugin.route('/')
def index():
    items = []

    context_items = []
    context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Clear Folders', 'XBMC.RunPlugin(%s)' % (plugin.url_for(clear))))
    context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Reset Cache', 'XBMC.RunPlugin(%s)' % (plugin.url_for(clear_cache))))
    items.append(
    {
        'label': "Folders",
        'path': plugin.url_for('subscribe'),
        'thumbnail':get_icon_path('tv'),
        'context_menu': context_items,
    })
    context_items = []
    context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Add Channel', 'XBMC.RunPlugin(%s)' % (plugin.url_for(add_channel))))
    context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Remove Channel', 'XBMC.RunPlugin(%s)' % (plugin.url_for(remove_channel))))
    context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Import Channels', 'XBMC.RunPlugin(%s)' % (plugin.url_for(import_channels))))
    context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Export Channels', 'XBMC.RunPlugin(%s)' % (plugin.url_for(export_channels))))
    context_items.append(("[COLOR yellow][B]%s[/B][/COLOR] " % 'Clear Channels', 'XBMC.RunPlugin(%s)' % (plugin.url_for(clear_channels))))
    items.append(
    {
        'label': "Channels",
        'path': plugin.url_for('channel_player'),
        'thumbnail':get_icon_path('tv'),
        'context_menu': context_items,
    })
    return items

if __name__ == '__main__':
    plugin.run()
    if big_list_view == True:
        view_mode = int(plugin.get_setting('view_mode'))
        plugin.set_view_mode(view_mode)