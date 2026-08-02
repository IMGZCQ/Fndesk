#!/bin/bash
# Shell CGI代理脚本（静态文件+修复JSON截断+支持Range+生产级防护）
set -uo pipefail
trap 'echo -e "Status: 500 Internal Server Error\nContent-Type: text/plain; charset=utf-8\n\nProxy Error: 脚本执行异常" >&2' ERR

# -------------------------- 全局配置项 --------------------------
# 静态文件配置
BASE_PATH="/var/apps/fndesk/target/server"  # 静态文件根目录（和基础版一致）
# 代理配置（和生产版一致）
TARGET_HOST="127.0.0.1"
TARGET_PORT="9990"
BASE_URL="http://${TARGET_HOST}:${TARGET_PORT}"
NGINX_MAX_SIZE=$((1 * 1024 * 1024))  # Nginx 1MB上传限制
# -------------------------- 配置项结束 --------------------------

# -------------------------- 1. 解析CGI请求信息（保留生产版逻辑） --------------------------
REQUEST_METHOD=${REQUEST_METHOD:-GET}
REQUEST_URI=${REQUEST_URI:-/}
URI_NO_QUERY=${REQUEST_URI%%\?*}
QUERY_STRING=${QUERY_STRING:-}

# 解析路径（生产版精准解析逻辑）
REL_PATH="/"
if [[ "$URI_NO_QUERY" == *index.cgi* ]]; then
    temp_path=$(echo "$URI_NO_QUERY" | awk -F 'index.cgi' '{print $NF}')
    if [[ -z "$temp_path" || "$temp_path" != /* ]]; then
        REL_PATH="/${temp_path}"
    else
        REL_PATH="$temp_path"
    fi
else
    REL_PATH="$URI_NO_QUERY"
fi
REL_PATH=${REL_PATH:-/}
[[ "$REL_PATH" == "" ]] && REL_PATH="/"

# -------------------------- 2. player.cgi 整合逻辑 --------------------------
# 如果有查询参数，且路径为空或根路径，走 player 流程
if [ -n "$QUERY_STRING" ] && ([ "$REL_PATH" = "/" ] || [ "$REL_PATH" = "" ]); then
    decode_uri() {
        local encoded="${1//+/ }"
        printf '%b' "${encoded//%/\\x}"
    }

    json_escape() {
        local s=$1
        s=${s//\\/\\\\}
        s=${s//\"/\\\"}
        printf '%s' "$s"
    }

    PATH_PARAM=""
    MODE_PARAM=""

    IFS='&' read -ra pairs <<< "$QUERY_STRING"
    for pair in "${pairs[@]}"; do
        [ -z "$pair" ] && continue
        key=${pair%%=*}
        val=""
        if [ "$pair" != "$key" ]; then
            val=${pair#*=}
        fi
        if [ "$key" = "path" ]; then
            PATH_PARAM=$(decode_uri "$val")
        elif [ "$key" = "mode" ]; then
            MODE_PARAM="$val"
        fi
    done

    if [ -z "$PATH_PARAM" ]; then
        echo "Status: 400 Bad Request"
        echo "Content-Type: text/plain; charset=utf-8"
        echo
        echo "missing path"
        exit 0
    fi

    if [ "$MODE_PARAM" != "stream" ] && [ "$MODE_PARAM" != "list" ]; then
        echo "Content-Type: text/html; charset=utf-8"
        echo
        cat <<'PLAYER_HTML'
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>Fndesk 音乐速听</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">
<style>
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
body{background:linear-gradient(135deg,#0f172a 0%,#1e293b 100%);color:#fff;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;width:100%;height:100%;min-height:100vh;display:flex;justify-content:center;align-items:center;padding:0;overflow:auto;margin:0;position:absolute;top:0;left:0;cursor:pointer;}
body::after{content:"";position:fixed;top:50%;left:50%;width:600px;height:600px;background:radial-gradient(circle,rgba(0,191,255,0.2) 0%,transparent 70%);border-radius:50%;transform:translate(-50%,-50%);z-index:-1;filter:blur(80px)}
.player-shell{width:100%;height:100%;max-width:100%;background:radial-gradient(circle,rgba(15,23,42,1) 0%,rgba(5,10,20,1) 100%);backdrop-filter:blur(12px);border:0 solid rgba(0,191,255,0.2);border-radius:0;padding:2vw 2vw 3vw;box-shadow:0 8px 32px rgba(0,0,0,0.4),0 0 15px rgba(0,191,255,0.1),inset 0 1px 0 rgba(255,255,255,0.05);position:relative;overflow:hidden;display:flex;flex-direction:column;justify-content:center;pointer-events:auto;}
.player-shell::before{content:"";position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,#00bfff,#1e90ff,#9370db,#00bfff);background-size:200% 100%;animation:g 5s linear infinite}
@keyframes g{0%{background-position:0% 0%}100%{background-position:200% 0%}}
.title{font-size:clamp(18px,4vw,22px);text-align:center;margin-bottom:3vw;font-weight:600;color:#e0f7ff;text-shadow:0 0 8px rgba(0,191,255,0.3);letter-spacing:.5px}
.big-controls{display:flex;justify-content:center;align-items:center;gap:4vw;margin-bottom:3vw;position:relative;flex-shrink:0}
.btn-circle{width:clamp(60px,15vw,80px);height:clamp(60px,15vw,80px);border-radius:50%;border:1px solid rgba(0,191,255,0.3);background:linear-gradient(135deg,#00bfff 0%,#1e90ff 100%);color:#fff;font-size:clamp(24px,6vw,32px);display:flex;justify-content:center;align-items:center;box-shadow:0 4px 15px rgba(0,191,255,0.4),inset 0 1px 0 rgba(255,255,255,0.2);cursor:pointer;transition:all .2s ease;position:relative;z-index:2}
.btn-circle::before{content:"";position:absolute;width:100%;height:100%;border-radius:50%;background:rgba(255,255,255,0.1);z-index:-1;transform:scale(.9);opacity:0;transition:all .2s ease}
.btn-circle:hover::before{opacity:1;transform:scale(1.05)}
.btn-circle:active{transform:scale(.95);box-shadow:0 2px 10px rgba(0,191,255,0.3)}
.btn-small{width:clamp(40px,12vw,60px);height:clamp(40px,12vw,60px);border-radius:50%;border:3px solid rgba(0,191,255,0.7);background:rgba(30,41,59,0.7);color:#00bfff;font-size:clamp(18px,4vw,22px);display:flex;justify-content:center;align-items:center;cursor:pointer;transition:all .2s ease;box-shadow:0 2px 8px rgba(0,0,0,0.3)}
.btn-small:hover{background:rgba(30,41,59,0.9);border-color:rgba(0,191,255,0.4);color:#87ceeb;transform:translateY(-2px)}
.btn-small:active{transform:scale(.96) translateY(0);background:rgba(15,23,42,0.9)}
.btn-circle i{font-size:clamp(26px,6vw,34px)}
.btn-circle i.fa-play{margin-left:clamp(5px,1vw,8px)}
.btn-small i{font-size:clamp(18px,4vw,22px)}
.progress-row{display:flex;align-items:center;gap:2vw;margin-bottom:2vw;position:relative;width:100%;flex-shrink:0}
.time-label{font-size:clamp(12px,2vw,13px);width:15%;min-width:40px;text-align:center;color:#87ceeb;text-shadow:0 0 4px rgba(0,191,255,0.2)}
.progress-bar{flex:1;-webkit-appearance:none;appearance:none;height:clamp(12px,3vw,16px);border-radius:999px;background:rgba(30,41,59,0.8);overflow:hidden;position:relative}
.progress-bar::before{content:"";position:absolute;top:0;left:0;height:100%;width:var(--progress-width,0%);background:linear-gradient(90deg,#00bfff,#1e90ff);border-radius:999px;z-index:1}
.progress-bar::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;width:clamp(20px,4vw,24px);height:clamp(20px,4vw,24px);border-radius:50%;background:#fff;border:2px solid #00bfff;box-shadow:0 0 10px rgba(0,191,255,0.8),0 0 20px rgba(0,191,255,0.5);cursor:pointer;position:relative;z-index:2;transition:all .1s ease}
.progress-bar::-webkit-slider-thumb:hover{transform:scale(1.2);box-shadow:0 0 15px rgba(0,191,255,1),0 0 25px rgba(0,191,255,0.7)}
.progress-bar::-moz-range-thumb{width:clamp(20px,4vw,24px);height:clamp(20px,4vw,24px);border-radius:50%;background:#fff;border:2px solid #00bfff;box-shadow:0 0 10px rgba(0,191,255,0.8),0 0 20px rgba(0,191,255,0.5);cursor:pointer;position:relative;z-index:2}
.progress-bar::-moz-range-track{height:clamp(12px,3vw,16px);border-radius:999px;background:rgba(30,41,59,0.8);border:1px solid rgba(0,191,255,0.1)}
.hint{font-size:clamp(11px,2vw,12px);text-align:center;color:#64748b;margin-top:2vw;letter-spacing:.3px}
.playlist-btn{width:24px;height:24px;display:flex;justify-content:center;align-items:center;cursor:pointer;color:#87ceeb;transition:all .2s ease;margin-left:5px}
.playlist-btn:hover{color:#00bfff;transform:scale(1.1)}
.playlist-container{width:100%;flex:1;min-height:0;background:rgba(15,23,42,0.8);backdrop-filter:blur(10px);overflow-y:auto;transition:all 0.3s ease;margin-top:10px;border-radius:8px;border:1px solid rgba(0,191,255,0.1);display:none}
.playlist-container.show{display:block}
.playlist-item{padding:10px 15px;cursor:pointer;border-bottom:1px solid rgba(255,255,255,0.05);transition:all 0.2s ease;font-size:14px;color:#cbd5e1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.playlist-item:hover{background:rgba(0,191,255,0.1);color:#fff}
.playlist-item.active{background:rgba(0,191,255,0.2);color:#00bfff;font-weight:bold;border-left:3px solid #00bfff}
.error-toast{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);background:rgba(15,23,42,0.95);color:#ff4444;padding:20px;border-radius:10px;text-align:center;z-index:100;border:1px solid rgba(255,68,68,0.5);box-shadow:0 0 30px rgba(0,0,0,0.8);display:none;width:85%;font-size:14px;line-height:1.6;backdrop-filter:blur(5px)}
.lyrics-container{width:100%;height:0;overflow:hidden;margin-top:2vw;text-align:center;font-size:14px;color:#cbd5e1;line-height:24px;transition:all 0.3s ease;position:relative;display:none}
.lyrics-container.show{height:96px;display:block}
.lyrics-container.full-height{flex:1;height:auto;min-height:96px}
.lyrics-content{position:absolute;width:100%;top:0;transition:transform 0.3s ease-out}
.lyrics-line{opacity:0.6;transition:all 0.2s ease;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding:0 5vw}
.lyrics-line.active{opacity:1;color:#00bfff;font-weight:bold;font-size:16px;text-shadow:0 0 10px rgba(0,191,255,0.5)}
.big-controls * {pointer-events: auto;}
.progress-row * {pointer-events: auto;}
.playlist-container * {pointer-events: auto;}
</style>
</head>
<body>
<div class="player-shell">
<div class="title" id="player-title"></div>
<div class="big-controls">
<button id="btn-random" class="btn-small" type="button" title="随机播放：关闭"><i class="fa fa-random"></i></button>
<button id="btn-prev-track" class="btn-small" type="button" title="上一曲"><i class="fa fa-step-backward"></i></button>
<button id="btn-backward" class="btn-small" type="button" title="快退5秒" style="display:none"><i class="fa fa-backward"></i></button>
<button id="btn-play" class="btn-circle" type="button" title="播放/暂停"><i class="fa fa-play"></i></button>
<button id="btn-forward" class="btn-small" type="button" title="快进5秒" style="display:none"><i class="fa fa-forward"></i></button>
<button id="btn-next-track" class="btn-small" type="button" title="下一曲"><i class="fa fa-step-forward"></i></button>
<button id="btn-loop" class="btn-small" type="button" title="循环模式：全部循环"><i class="fa fa-reply-all"></i></button>
</div>
<div class="progress-row">
<div id="current-time" class="time-label">0:00</div>
<input id="progress" class="progress-bar" type="range" min="0" max="100" value="0">
<div id="duration" class="time-label">--:--</div>
<div id="lyrics-toggle" class="playlist-btn" title="歌词开关"><i class="fa fa-file-text-o"></i></div>
<div id="playlist-toggle" class="playlist-btn" title="播放列表"><i class="fa fa-list-ul"></i></div>
</div>
<div id="lyrics-container" class="lyrics-container"><div id="lyrics-content" class="lyrics-content"></div></div>
<div id="playlist-container" class="playlist-container"></div>
<div id="error-toast" class="error-toast"></div>
<div class="hint">双击空白区域播放/暂停 | 飞牛桌面管理工具</div>
</div>
<audio id="audio" preload="auto" playsinline>
<script>
!function(){
var a=document.getElementById('audio'),b=document.getElementById('btn-play'),c=document.getElementById('btn-backward'),d=document.getElementById('btn-forward'),x=document.getElementById('btn-prev-track'),y=document.getElementById('btn-next-track'),randBtn=document.getElementById('btn-random'),loopBtn=document.getElementById('btn-loop'),plistToggle=document.getElementById('playlist-toggle'),plistContainer=document.getElementById('playlist-container'),e=document.getElementById('progress'),f=document.getElementById('current-time'),g=document.getElementById('duration'),h=b?b.querySelector('i'):null,loopIcon=loopBtn?loopBtn.querySelector('i'):null,p=null,pi=-1,randActive=!1,loopMode='all',plistShow=!1,lyricsShow=!1,lrcData=[],lrcToggle=document.getElementById('lyrics-toggle'),lrcContainer=document.getElementById('lyrics-container'),lrcContent=document.getElementById('lyrics-content');
try{
  var sr=window.localStorage.getItem('fndesk_player_random');
  if(sr==='1')randActive=!0;
  var sl=window.localStorage.getItem('fndesk_player_loop');
  if(sl==='one'||sl==='none'||sl==='all')loopMode=sl;
  var sp=window.localStorage.getItem('fndesk_player_plist');
  if(sp==='1')plistShow=!0;
  var sly=window.localStorage.getItem('fndesk_player_lyrics');
  if(sly==='1')lyricsShow=!0;
}catch(t){}
function r(){
  try{
    var t=window.parent.document,n=t.querySelectorAll('[alt^="Fndesk 音乐速听"].pointer-events-none.mr-2.block.size-loose.select-none');
    n.forEach(function(t){
      var n=t.parentElement;
      if(n&&(n=n.parentElement)&&(n=n.parentElement)&&(n=n.parentElement)){
        var targetWidth='420px';
        var h=280;
        if(plistShow)h+=320;
        if(lyricsShow)h+=96;
        var targetHeight=h+'px';
        if(n.style.height!==targetHeight){
             n.style.width=targetWidth;
             n.style.height=targetHeight;
        }
      }
    });
  }catch(t){}
}

function updateLyricsLayout(){
  if(lrcContainer){
    if(lyricsShow){
      lrcContainer.style.display='block';
      if(!plistShow){
         lrcContainer.classList.add('full-height');
         lrcContainer.classList.remove('show');
      }else{
         lrcContainer.classList.remove('full-height');
         lrcContainer.classList.add('show');
      }
    }else{
      lrcContainer.style.display='none';
      lrcContainer.classList.remove('full-height');
      lrcContainer.classList.remove('show');
    }
  }
}
function parseLrc(txt){
  if(typeof txt!=='string')txt=String(txt);
  var lines=txt.split(/\r?\n|\r/);
  var tempLyrics=[];
  var timeRegex=/\[(\d{1,3}):(\d{2})(?::(\d{2}))?(?:\.(\d{1,3}))?]/g;
  
  for(var i=0;i<lines.length;i++){
    var line=lines[i].trim();
    if(!line)continue;
    
    var match;
    var hasMatch=false;
    
    timeRegex.lastIndex=0;
    while((match=timeRegex.exec(line))!==null){
      hasMatch=true;
      var hasThirdNumber=match[3]!==undefined;
      var hasMilliseconds=match[4]!==undefined;
      
      var hours=0,minutes=0,seconds=0,milliseconds=0;
      
      if(hasThirdNumber){
        hours=parseInt(match[1]);
        minutes=parseInt(match[2]);
        seconds=parseInt(match[3]);
        if(hasMilliseconds){
            var msStr=match[4];
            if(msStr.length===2) milliseconds=parseInt(msStr)*10;
            else if(msStr.length===1) milliseconds=parseInt(msStr)*100;
            else milliseconds=parseInt(msStr);
        }
      }else{
        minutes=parseInt(match[1]);
        seconds=parseInt(match[2]);
        if(hasMilliseconds){
            var msStr=match[4];
            if(msStr.length===2) milliseconds=parseInt(msStr)*10;
            else if(msStr.length===1) milliseconds=parseInt(msStr)*100;
            else milliseconds=parseInt(msStr);
        }
      }
      
      var totalTime=hours*3600+minutes*60+seconds+milliseconds/1000;
      var text=line.replace(/\[\d{1,3}:\d{2}(?::\d{2})?(?:\.\d{1,3})?]/g,'').trim();
      
      if(text){
        tempLyrics.push({time:totalTime,text:text});
      }
    }
    
    if(!hasMatch&&line&&tempLyrics.length===0){
       tempLyrics.push({time:0,text:line});
    }
  }
  
  tempLyrics.sort(function(a,b){return a.time-b.time;});
  
  var uniqueLyrics=[];
  for(var i=0;i<tempLyrics.length;i++){
    if(i===0||tempLyrics[i].text!==tempLyrics[i-1].text){
       uniqueLyrics.push(tempLyrics[i]);
    }
  }
  return uniqueLyrics;
}
function loadLrc(path){
  if(!lyricsShow)return;
  lrcContent.innerHTML='<div class="lyrics-line">加载歌词中...</div>';
  lrcContent.style.top='50%';
  lrcContent.style.transform='translateY(-50%)';
  var lrcPath=path.replace(/\.[^/.]+$/, "") + ".lrc";
  fetch('?mode=stream&path='+encodeURIComponent(lrcPath)).then(function(r){
    if(r.ok){
      return r.arrayBuffer();
    }
    throw new Error('No lrc');
  }).then(function(buffer){
    var decoder;
    if(buffer.byteLength>=2){
      var view=new DataView(buffer);
      var b1=view.getUint8(0);
      var b2=view.getUint8(1);
      if(b1===0xFF&&b2===0xFE)decoder=new TextDecoder('utf-16le');
      else if(b1===0xFE&&b2===0xFF)decoder=new TextDecoder('utf-16be');
    }
    if(!decoder)decoder=new TextDecoder('utf-8');
    var txt=decoder.decode(buffer);
    if(txt.indexOf('\uFFFD')!==-1||!/\[\d{2}:\d{2}/.test(txt)){
      try{
        var gbkDecoder=new TextDecoder('gbk');
        var txtGbk=gbkDecoder.decode(buffer);
        if(/\[\d{2}:\d{2}/.test(txtGbk)){
          txt=txtGbk;
        }
      }catch(e){}
    }
    lrcData=parseLrc(txt);
    if(lrcData.length===0){
       lrcContent.innerHTML='<div class="lyrics-line" style="white-space:normal;overflow:visible;text-overflow:clip;">暂无LRC歌词</div>';
       lrcContent.style.top='50%';
       lrcContent.style.transform='translateY(-50%)';
       lrcContent.style.fontSize='2em';
       lrcContent.style.lineHeight='1.2em';
    }else{
       lrcContent.style.top='0';
       lrcContent.style.transform='translateY(36px)';
       lrcContent.style.fontSize='';
       lrcContent.style.lineHeight='';
       renderLrcLines();
    }
  }).catch(function(){
    lrcData=[];
    lrcContent.innerHTML='<div class="lyrics-line" style="white-space:normal;overflow:visible;text-overflow:clip;">暂无歌词文件</div>';
    lrcContent.style.top='50%';
    lrcContent.style.transform='translateY(-50%)';
    lrcContent.style.fontSize='2em';
    lrcContent.style.lineHeight='1.2em';
  });
}
function renderLrcLines(){
  var html='';
  for(var i=0;i<lrcData.length;i++){
    html+='<div class="lyrics-line" id="lrc-'+i+'">'+lrcData[i].text+'</div>';
  }
  lrcContent.innerHTML=html;
}
function updateLrc(t){
  if(!lyricsShow||!lrcData.length)return;
  var idx=-1;
  for(var i=0;i<lrcData.length;i++){
    if(t>=lrcData[i].time){
      idx=i;
    }else{
      break;
    }
  }
  var lines=lrcContent.querySelectorAll('.lyrics-line');
  lines.forEach(function(l){l.classList.remove('active');});
  if(idx>=0){
     var active=document.getElementById('lrc-'+idx);
     if(active){
       active.classList.add('active');
       var containerHeight=lrcContainer.clientHeight||96;
       var centerPos=containerHeight/2;
       var offset=centerPos-(idx*24+12);
       lrcContent.style.transform='translateY('+offset+'px)';
     }
  }
}
function toggleLrc(){
  if(!lrcContainer||!lrcToggle)return;
  try{window.localStorage.setItem('fndesk_player_lyrics',lyricsShow?'1':'0');}catch(t){}
  
  updateLyricsLayout();
  
  if(lyricsShow){
    lrcToggle.style.color='#00ff9a';
    if(p&&pi>=0)loadLrc(p[pi].path);
  }else{
    lrcToggle.style.color='#87ceeb';
  }
  r();
}
function playTrack(index){
  if(index<0||!p||index>=p.length)return;
  pi=index;
  var item=p[pi];
  
  var titleEl=document.querySelector('.title');
  if(titleEl)titleEl.textContent=item.name;
  
  var newUrl = '?path='+encodeURIComponent(item.path);
  window.history.replaceState(null, '', newUrl);
  
  if(a){
    a.src='?mode=stream&path='+encodeURIComponent(item.path);
    a.play().catch(function(){
       if(a.error)checkError();
    });
  }
  
  loadLrc(item.path);
  
  renderPlaylist(); 
  
  if(e)e.value=0;
  if(f)f.textContent='0:00';
  if(g)g.textContent='--:--';
  if(e)e.style.setProperty('--progress-width','0%');
}
function renderPlaylist(){
  if(!plistContainer||!p)return;
  plistContainer.innerHTML='';
  p.forEach(function(item,index){
    var div=document.createElement('div');
    div['className']='playlist-item'+(index===pi?' active':'');
    div.textContent=(index+1)+'. '+item.name;
    div.title=item.name;
    div.onclick=function(){
      if(index!==pi){
        playTrack(index);
      }
    };
    plistContainer.appendChild(div);
  });
  if(pi>=0){
    var activeItem=plistContainer.querySelectorAll('.playlist-item')[pi];
    if(activeItem)activeItem.scrollIntoView({block:'nearest'});
  }
}
function m(t){
  return isFinite(t)&&t>=0?(Math.floor(t/60)+':'+(Math.floor(t%60)<10?'0'+Math.floor(t%60):Math.floor(t%60))):'--:--';
}
function u(){
  h&&(h.className=a&&!a.paused?'fa fa-pause':'fa fa-play');
}
function q(){
  if(randBtn){
    randBtn.style.opacity=randActive?1:0.6;
    randBtn.style.color=randActive?'#00ff9a':'#00bfff';
    randBtn.title=randActive?'随机播放：开启':'随机播放：关闭';
    try{window.localStorage.setItem('fndesk_player_random',randActive?'1':'0');}catch(t){}
  }
}
function z(){
  if(!loopBtn||!loopIcon)return;
  try{window.localStorage.setItem('fndesk_player_loop',loopMode);}catch(t){}
  if('none'===loopMode){
    loopIcon.className='fa fa-reply';
    loopBtn.style.opacity=0.4;
    loopBtn.title='不循环';
  }else if('one'===loopMode){
    loopIcon.className='fa fa-reply';
    loopBtn.style.opacity=1;
    loopBtn.title='单曲循环';
  }else{
    loopIcon.className='fa fa-reply-all';
    loopBtn.style.opacity=1;
    loopBtn.title='目录循环';
  }
}
function l(){
  var t=window.location.search;
  if(t){
    var n=new URLSearchParams(t),o=n.get('path');
    if(o){
      var s=o;
      try{s=decodeURIComponent(o);}catch(t){}
      
      if(lyricsShow){
        loadLrc(s);
      }
      
      if(a){
        a.src='?mode=stream&path='+encodeURIComponent(s);
      }
      
      var titleEl = document.getElementById('player-title');
      if(titleEl){
        var fileName = s.split('/').pop();
        titleEl.textContent = decodeURIComponent(fileName);
      }
      
      fetch('?mode=list&path='+encodeURIComponent(s)).then(function(t){
        return t.ok?t.json():null;
      }).then(function(t){
        if(t){
          if(Array.isArray(t)){
            p=t;
          }else if(Array.isArray(t.items)){
            p=t.items;
          }else{
            return;
          }
          pi=-1;
          for(var n=0;n<p.length;n++){
            if(p[n]&&p[n].path===s){
              pi=n;
              break;
            }
          }
          if(pi<0&&p.length>0){
            pi=0;
          }
          if(p&&p.length){
            var prevIndex=pi-1<0?p.length-1:pi-1;
            var nextIndex=pi+1>=p.length?0:pi+1;
            var prevItem=p[prevIndex];
            var nextItem=p[nextIndex];
            if(x){
              x.title=prevItem&&prevItem.name?prevItem.name:'上一曲';
            }
            if(y){
              y.title=nextItem&&nextItem.name?nextItem.name:'下一曲';
            }
          }
          renderPlaylist();
        }
      }).catch(function(t){});
    }
  }
}
function v(){
  if(randActive){
     A();
     return;
  }
  if(p&&p.length){
    pi<0&&(pi=0);
    var t=pi+1;
    t>=p.length&&(t=0);
    playTrack(t);
  }
}
function w(){
  if(p&&p.length){
    pi<0&&(pi=0);
    var t=pi-1;
    t<0&&(t=p.length-1);
    playTrack(t);
  }
}
function k(){
  a&&isFinite(a.duration)&&(e.style.setProperty('--progress-width',(a.currentTime/a.duration)*100+'%'));
}
function A(){
  if(p&&p.length){
    var t=pi;
    t<0&&(t=0);
    var n=p.length<=1?t:Math.floor(Math.random()*p.length);
    var o=0;
    while(p.length>1&&n===t&&o<8){
      n=Math.floor(Math.random()*p.length);
      o++;
    }
    playTrack(n);
  }else{
    v();
  }
}
function B(){
  if('one'===loopMode){
    if(a){
      a.currentTime=0;
      a.play();
    }
    return;
  }
  if('none'===loopMode){
    return;
  }
  if(randActive){
    A();
  }else{
    v();
  }
}
function C(){
  if(!plistContainer||!plistToggle)return;
  try{window.localStorage.setItem('fndesk_player_plist',plistShow?'1':'0');}catch(t){}
  
  updateLyricsLayout();
  
  if(plistShow){
    plistContainer.classList.add('show');
    plistToggle.style.color='#00ff9a';
  }else{
    plistContainer.classList.remove('show');
    plistToggle.style.color='#87ceeb';
  }
  r();
}

function togglePlayPause() {
  if (!a) return;
  
  if (!p || p.length === 0) {
    l();
    setTimeout(() => {
      if (p && p.length > 0) {
        playTrack(0);
      } else {
        a.play().catch(err => {
          console.log('播放需要用户交互', err);
        });
      }
    }, 100);
    return;
  }
  
  if (a.paused) {
    a.play().catch(err => {
      console.log('播放失败', err);
    });
  } else {
    a.pause();
  }
}

document.addEventListener('dblclick', function(e) {
  const isControlElement = e.target.closest('.big-controls, .progress-row, .playlist-container, .lyrics-container');
  if (!isControlElement) {
    togglePlayPause();
  }
});

let audioContext;
function keepAudioContextAlive() {
  try {
    if (!audioContext) {
      audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioContext.state === 'suspended') {
      audioContext.resume();
    }
  } catch (e) {
  }
}

document.addEventListener('click', keepAudioContextAlive);
document.addEventListener('dblclick', keepAudioContextAlive);

r();
C();
toggleLrc();
l();
if(b){
  b.addEventListener('click',function(){
    a&&(a.paused?a.play():a.pause());
  });
}
if(lrcToggle){
  lrcToggle.addEventListener('click',function(){
    lyricsShow=!lyricsShow;
    toggleLrc();
  });
}
if(lrcContainer){
  lrcContainer.addEventListener('dblclick',function(){
    a&&(a.paused?a.play():a.pause());
  });
}
if(c){
  c.addEventListener('click',function(){
    a&&isFinite(a.currentTime)&&(a.currentTime=Math.max(0,a.currentTime-5),k());
  });
}
if(d){
  d.addEventListener('click',function(){
    a&&isFinite(a.currentTime)&&isFinite(a.duration)&&(a.currentTime=Math.min(a.duration,a.currentTime+5),k());
  });
}
if(randBtn){
  q();
  randBtn.addEventListener('click',function(){
    randActive=!randActive;
    q();
  });
}
if(loopBtn){
  z();
  loopBtn.addEventListener('click',function(){
    if('all'===loopMode){
      loopMode='one';
    }else if('one'===loopMode){
      loopMode='none';
    }else{
      loopMode='all';
    }
    z();
  });
}
if(plistToggle){
  plistToggle.addEventListener('click',function(){
    plistShow=!plistShow;
    C();
  });
}
if(x){
  x.addEventListener('click',w);
}
if(y){
  y.addEventListener('click',v);
}
if(e){
  e.addEventListener('input',function(){
    a&&isFinite(a.duration)&&(a.currentTime=a.duration*(e.value/100),k());
  });
}
if(a){
  a.addEventListener('timeupdate',function(){
    a&&isFinite(a.duration)&&(e.value=isFinite((a.currentTime/a.duration)*100)?(a.currentTime/a.duration)*100:0,f.textContent=m(a.currentTime),k());
    updateLrc(a.currentTime);
  });
  a.addEventListener('loadedmetadata',function(){
    g.textContent=m(a.duration);
  });
  a.addEventListener('play',u);
  a.addEventListener('pause',u);
  a.addEventListener('ended',B);
  function checkError(){
    var src=a.src;
    if(src){
      fetch(src).then(function(r){
        r.text().then(function(t){
          if(t&&(t.indexOf('ffmpeg_not_installed')!==-1||t.indexOf('ffmpeg')!==-1)){
            var msg="播放无损格式需要系统先安装ffmpeg<br>安装命令：apt update && apt install -y ffmpeg";
            var toast=document.getElementById('error-toast');
            if(toast){
              toast.innerHTML=msg;
              toast.style.display='block';
            }
            var h=document.querySelector('.hint');
            if(h){
              h.style.color='#ff4444';
              h.textContent='系统缺少ffmpeg组件，无法播放';
            }
          }
        });
      });
    }
  }
  a.addEventListener('error',checkError);
}
window.addEventListener('load',function(){
  try{
    if(a){
      a.play().catch(function(){
        if(a.error)checkError();
      });
    }
  }catch(t){}
});
}();
</script>
</body>
</html>
PLAYER_HTML
    exit 0
  fi

  FILE_PATH="$PATH_PARAM"

  # 安全校验：只拦截真正的路径遍历（/../、../开头、/..结尾）
  if [[ "$FILE_PATH" == *"/../"* ]] || [[ "$FILE_PATH" == "../"* ]] || [[ "$FILE_PATH" == *"/.." ]]; then
      echo "Status: 400 Bad Request"
      echo "Content-Type: text/plain; charset=utf-8"
      echo
      echo "bad path"
      exit 0
  fi

  if [ -z "$FILE_PATH" ]; then
      echo "Status: 400 Bad Request"
      echo "Content-Type: text/plain; charset=utf-8"
      echo
      echo "missing path"
      exit 0
  fi

  case "$FILE_PATH" in
      /vol* | /var/apps/fndesk/target/server/MP3/* )
          ;;
      * )
          echo "Status: 403 Forbidden"
          echo "Content-Type: text/plain; charset=utf-8"
          echo
          echo "forbidden"
          exit 0
          ;;
  esac

  if [ "$MODE_PARAM" = "list" ]; then
      if [ -d "$FILE_PATH" ]; then
          DIR_PATH="$FILE_PATH"
      else
          if [ ! -f "$FILE_PATH" ]; then
              echo "Status: 404 Not Found"
              echo "Content-Type: text/plain; charset=utf-8"
              echo
              echo "file not found"
              exit 0
          fi
          DIR_PATH=$(dirname "$FILE_PATH")
      fi
      echo "Content-Type: application/json; charset=utf-8"
      echo
      printf '['
      first=1
      while IFS= read -r f; do
          [ -z "$f" ] && continue
          name=${f##*/}
          lower=${name,,}
          case "$lower" in
              *.mp3|*.wav|*.flac|*.ogg|*.m4a|*.aac|*.ape|*.dsf|*.dff|*.wv|*.wma|*.dts|*.ac3|*.eac3|*.aiff|*.aif|*.mka|*.tak|*.tta|*.mpc|*.opus) ;;
              *) continue ;;
          esac
          name_json=$(json_escape "$name")
          path_json=$(json_escape "$f")
          if [ $first -eq 0 ]; then
              printf ','
          fi
          printf '{"name":"%s","path":"%s"}' "$name_json" "$path_json"
          first=0
      done < <(find "$DIR_PATH" -maxdepth 1 -type f 2>/dev/null | awk -F/ '{print $NF "\t" $0}' | sort | cut -f2-)
      printf ']'
      echo
      exit 0
  fi

  if [ ! -f "$FILE_PATH" ]; then
      echo "Status: 404 Not Found"
      echo "Content-Type: text/plain; charset=utf-8"
      echo
      echo "file not found"
      exit 0
  fi

  ext=${FILE_PATH##*.}
  mime="application/octet-stream"
  case "${ext,,}" in
      mp3) mime="audio/mpeg" ;;
      wav) mime="audio/wav" ;;
      flac) mime="audio/flac" ;;
      ogg) mime="audio/ogg" ;;
      m4a) mime="audio/mp4" ;;
      aac) mime="audio/aac" ;;
      lrc) mime="text/plain" ;;
      ape|dsf|dff|wv|wma|dts|ac3|eac3|aiff|aif|mka|tak|tta|mpc|opus)
          if ! command -v ffmpeg >/dev/null 2>&1; then
              echo "Status: 501 Not Implemented"
              echo "Content-Type: text/plain; charset=utf-8"
              echo
              echo "Error: ffmpeg_not_installed"
              exit 0
          fi

          CACHE_DIR="/tmp/fndesk_music"
          mkdir -p "$CACHE_DIR" 2>/dev/null

          if command -v md5sum >/dev/null 2>&1; then
              HASH_NAME=$(echo -n "$FILE_PATH" | md5sum | awk '{print $1}')
          else
              HASH_NAME="${FILE_PATH//\//_}"
          fi
          
          TARGET_MP3="${CACHE_DIR}/${HASH_NAME}.mp3"
           LOCK_DIR="${CACHE_DIR}/${HASH_NAME}.lock"

           (find "$CACHE_DIR" -type f -name "*.mp3" -mtime +5 -delete >/dev/null 2>&1) &

           if [ -f "$TARGET_MP3" ]; then
                SIZE=$(stat -c%s "$TARGET_MP3" 2>/dev/null || stat -f%z "$TARGET_MP3" 2>/dev/null || echo 0)
                if [ "$SIZE" -gt 1048576 ]; then
                    FILE_PATH="$TARGET_MP3"
                    mime="audio/mpeg"
                    touch "$TARGET_MP3" 2>/dev/null
                fi
           fi

          if [ "$mime" != "audio/mpeg" ]; then
              WAIT_COUNT=0
              while [ -d "$LOCK_DIR" ]; do
                  if [ $WAIT_COUNT -ge 30 ]; then
                       echo "Status: 503 Service Unavailable"
                       echo "Content-Type: text/plain; charset=utf-8"
                       echo
                       echo "Transcoding timeout"
                       exit 0
                  fi
                  sleep 1
                  WAIT_COUNT=$((WAIT_COUNT+1))
              done

              if [ -f "$TARGET_MP3" ]; then
                   SIZE=$(stat -c%s "$TARGET_MP3" 2>/dev/null || stat -f%z "$TARGET_MP3" 2>/dev/null || echo 0)
                   if [ "$SIZE" -gt 1048576 ]; then
                       FILE_PATH="$TARGET_MP3"
                       mime="audio/mpeg"
                   fi
              fi
          fi

          if [ "$mime" != "audio/mpeg" ]; then
               if mkdir "$LOCK_DIR" 2>/dev/null; then
                   ffmpeg -i "$FILE_PATH" -map 0:a -b:a 320k -y "$TARGET_MP3" < /dev/null >/dev/null 2>&1
                   
                   rmdir "$LOCK_DIR"
                   
                   if [ -f "$TARGET_MP3" ]; then
                       SIZE=$(stat -c%s "$TARGET_MP3" 2>/dev/null || stat -f%z "$TARGET_MP3" 2>/dev/null || echo 0)
                       if [ "$SIZE" -gt 1048576 ]; then
                           FILE_PATH="$TARGET_MP3"
                           mime="audio/mpeg"
                       else
                           rm -f "$TARGET_MP3"
                           echo "Status: 500 Internal Server Error"
                           echo "Content-Type: text/plain; charset=utf-8"
                           echo
                           echo "Transcoding failed or file too small"
                           exit 0
                       fi
                   else
                       echo "Status: 500 Internal Server Error"
                       echo "Content-Type: text/plain; charset=utf-8"
                       echo
                       echo "Transcoding failed"
                       exit 0
                   fi
               else
                   echo "Status: 503 Service Unavailable"
                   echo "Content-Type: text/plain; charset=utf-8"
                   echo
                   echo "Server busy"
                   exit 0
               fi
          fi
          ;;
      *) 
          echo "Status: 403 Forbidden"
          echo "Content-Type: text/plain; charset=utf-8"
          echo
          echo "unsupported file type"
          exit 0
          ;;
  esac

  FILE_SIZE=$(stat -c%s "$FILE_PATH" 2>/dev/null || stat -f%z "$FILE_PATH" 2>/dev/null || echo "")
  if [ -z "$FILE_SIZE" ]; then
      echo "Status: 500 Internal Server Error"
      echo "Content-Type: text/plain; charset=utf-8"
      echo
      echo "cannot get file size"
      exit 0
  fi

  RANGE_HEADER=${HTTP_RANGE:-}

  if [ -z "$RANGE_HEADER" ]; then
      echo "Content-Type: $mime"
      echo "Accept-Ranges: bytes"
      echo "Content-Length: $FILE_SIZE"
      echo
      cat "$FILE_PATH"
      exit 0
  fi

  case "$RANGE_HEADER" in
      bytes=* )
          ;;
      * )
          echo "Status: 416 Range Not Satisfiable"
          echo "Content-Range: bytes */$FILE_SIZE"
          echo
          exit 0
          ;;
  esac

  RANGE=${RANGE_HEADER#bytes=}
  START=${RANGE%-*}
  END=${RANGE#*-}

  if [ -z "$START" ]; then
      echo "Status: 416 Range Not Satisfiable"
      echo "Content-Range: bytes */$FILE_SIZE"
      echo
      exit 0
  fi

  if [ -z "$END" ] || [ "$END" = "$START" ]; then
      END=$((FILE_SIZE - 1))
  fi

  if ! [ "$START" -ge 0 ] 2>/dev/null || ! [ "$END" -ge 0 ] 2>/dev/null || [ "$START" -ge "$FILE_SIZE" ]; then
      echo "Status: 416 Range Not Satisfiable"
      echo "Content-Range: bytes */$FILE_SIZE"
      echo
      exit 0
  fi

  if [ "$END" -ge "$FILE_SIZE" ]; then
      END=$((FILE_SIZE - 1))
  fi

  CHUNK_SIZE=$((END - START + 1))

  echo "Status: 206 Partial Content"
  echo "Content-Type: $mime"
  echo "Accept-Ranges: bytes"
  echo "Content-Length: $CHUNK_SIZE"
  echo "Content-Range: bytes $START-$END/$FILE_SIZE"
  echo

  BUFSIZE=$((2 * 1024 * 1024))
  dd if="$FILE_PATH" \
   bs="$BUFSIZE" \
   skip="$START" \
   count="$CHUNK_SIZE" \
   iflag=skip_bytes,count_bytes \
   status=none 2>/dev/null
  exit 0
fi

# -------------------------- 3. 开机时间检查 --------------------------
# 获取系统开机时间（秒）
UPTIME=$(cat /proc/uptime 2>/dev/null | awk '{print $1}' | cut -d. -f1)
MIN_UPTIME=180  # 3分钟 = 180秒

# 如果开机时间不足3分钟，检查是否需要重定向
if [ -n "$UPTIME" ] && [ "$UPTIME" -lt "$MIN_UPTIME" ]; then
    # 允许的路径（支持包含 index.cgi 的路径）
    ALLOWED_PATHS=("/loading.html" "/api/system-status" "/api/update-data")
    IS_ALLOWED="false"
    
    # 检查当前路径是否在允许列表中
    for allowed in "${ALLOWED_PATHS[@]}"; do
        if [[ "$REL_PATH" == *"$allowed" ]]; then
            IS_ALLOWED="true"
            break
        fi
    done
    
    # 如果不在允许列表中，重定向到 loading.html（保持相同的访问前缀）
    if [ "$IS_ALLOWED" = "false" ]; then
        # 构建正确的重定向路径（保留 index.cgi 前缀）
        if [[ "$URI_NO_QUERY" == *index.cgi* ]]; then
            REDIRECT_URL=$(echo "$URI_NO_QUERY" | sed "s|index.cgi/.*|index.cgi/loading.html|")
        else
            REDIRECT_URL="/loading.html"
        fi
        
        echo "Status: 302 Found"
        echo "Location: $REDIRECT_URL"
        echo "Content-Type: text/html; charset=utf-8"
        echo ""
        exit 0
    fi
fi

# -------------------------- 4. 静态文件优先处理逻辑 --------------------------
# 步骤1：处理静态文件路径（根路径默认index.html）
STATIC_REL_PATH="$REL_PATH"
if [ -z "$STATIC_REL_PATH" ] || [ "$STATIC_REL_PATH" = "/" ]; then
    STATIC_REL_PATH="/index.html"
fi

# 步骤2：拼接静态文件完整路径
TARGET_STATIC_FILE="${BASE_PATH}${STATIC_REL_PATH}"

# 步骤3：安全校验（防路径遍历，和基础版一致）
if echo "$TARGET_STATIC_FILE" | grep -q '\.\.'; then
    echo "Status: 400 Bad Request"
    echo "Content-Type: text/plain; charset=utf-8"
    echo ""
    echo "Bad Request: 禁止越级访问"
    exit 0
fi

# 步骤4：如果静态文件存在，返回静态文件（不走代理）
if [ -f "$TARGET_STATIC_FILE" ]; then
    # 识别文件后缀，设置MIME类型（和基础版一致）
    ext="${TARGET_STATIC_FILE##*.}"
case "$ext" in
        # 网页相关
        html|htm) mime="text/html; charset=utf-8" ;;
        css) mime="text/css; charset=utf-8" ;;
        js) mime="application/javascript; charset=utf-8" ;;
        # 图片格式
        jpg|jpeg) mime="image/jpeg" ;;
        png) mime="image/png" ;;
        gif) mime="image/gif" ;;
        svg) mime="image/svg+xml" ;;
        webp) mime="image/webp" ;;
        ico) mime="image/x-icon" ;;
        # 音频格式
        mp3) mime="audio/mpeg" ;;
        mp4) mime="video/mp4" ;;
        ogg) mime="audio/ogg" ;;
        flac) mime="audio/flac" ;;
        wav) mime="audio/wav" ;;       # 新增 WAV 音频
        aac) mime="audio/aac" ;;       # 新增 AAC 音频
        # 文本格式
        txt|log) mime="text/plain; charset=utf-8" ;;
        # 字体文件（高频静态资源）
        woff) mime="font/woff" ;;
        woff2) mime="font/woff2" ;;
        ttf) mime="font/ttf" ;;
        eot) mime="application/vnd.ms-fontobject" ;;
        # 其他未匹配类型
        *) mime="application/octet-stream" ;;
esac

    # 返回静态文件
    echo "Content-Type: $mime"
    echo ""
    cat "$TARGET_STATIC_FILE"
    exit 0
fi
# -------------------------- 静态文件逻辑结束 --------------------------

# -------------------------- 5. 原有生产版代理逻辑（完全保留，无修改） --------------------------
# 拼接目标URL
if [[ -n "$QUERY_STRING" ]]; then
    TARGET_URL="${BASE_URL}${REL_PATH}?${QUERY_STRING}"
else
    TARGET_URL="${BASE_URL}${REL_PATH}"
fi
TARGET_URL=$(echo "$TARGET_URL" | sed 's|//|/|g' | sed 's|http:/|http://|g')

# 内网地址重定向判断
CURRENT_HOST=${HTTP_HOST%%:*}
INTERNAL_NETWORKS=("10." "172.16." "172.17." "172.18." "172.19." "172.20." "172.21." "172.22." "172.23." "172.24." "172.25." "172.26." "172.27." "172.28." "172.29." "172.30." "172.31." "192.168." "127.")
for network in "${INTERNAL_NETWORKS[@]}"; do
    if [[ "$CURRENT_HOST" == "$network"* ]]; then
        REDIRECT_URL="http://${CURRENT_HOST}:${TARGET_PORT}${REL_PATH}"
        if [[ -n "$QUERY_STRING" ]]; then
            REDIRECT_URL="${REDIRECT_URL}?${QUERY_STRING}"
        fi
        echo "Status: 302 Found"
        echo "Location: ${REDIRECT_URL}"
        echo "Content-Type: text/html; charset=utf-8"
        echo ""
        echo "<script>window.location.href='${REDIRECT_URL}';</script>"
        exit 0
    fi
done

# 安全校验
if echo "$REL_PATH" | grep -qi '\.\.' || echo "$REL_PATH" | grep -qi '%2e%2e' || echo "$REL_PATH" | grep -qi '%2f'; then
    echo "Status: 400 Bad Request"
    echo "Content-Type: text/html; charset=utf-8"
    echo ""
    echo "<script>alert('错误：禁止越级访问或非法路径字符！');history.back();</script>"
    exit 0
fi

# 1MB上传限制友好提示
CONTENT_LENGTH=${CONTENT_LENGTH:-0}
if [[ "$REQUEST_METHOD" == "POST" && $CONTENT_LENGTH -gt $NGINX_MAX_SIZE ]]; then
    echo "Status: 413 Request Entity Too Large"
    echo "Content-Type: text/html; charset=utf-8"
    echo ""
    echo "<!DOCTYPE html>"
    echo "<html><head><meta charset='utf-8'></head><body>"
    echo "<script>"
    echo "alert('文件大小超过限制！\\n当前仅支持上传≤1MB的文件，请压缩文件后重试。');"
    echo "history.back();"
    echo "</script>"
    echo "</body></html>"
    exit 0
fi

# 核心：修复JSON截断的代理逻辑
CURL_OPTS=("-i" "--connect-timeout" "60" "--max-time" "300" "--path-as-is" "--show-error" "-s" "--compressed")

# 处理请求头
HEADER_ARGS=()
for var in "${!HTTP_@}"; do
    header_name=$(echo "${var#HTTP_}" | tr '[:upper:]' '[:lower:]' | sed 's/_/-/g' | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) substr($i,2)} 1' OFS='-')
    header_value="${!var}"
    HEADER_ARGS+=("-H" "$header_name: $header_value")
done

case "$REQUEST_METHOD" in
    GET)
        curl "${CURL_OPTS[@]}" "${HEADER_ARGS[@]}" "$TARGET_URL"
        ;;

    POST)
        if [[ -z "${HTTP_CONTENT_TYPE:-}" ]]; then
            HEADER_ARGS+=("-H" "Content-Type: ${CONTENT_TYPE:-application/x-www-form-urlencoded}")
        fi
        
        if [[ $CONTENT_LENGTH -gt 0 ]]; then
            cat | curl "${CURL_OPTS[@]}" -X POST "${HEADER_ARGS[@]}" --data-binary @- "$TARGET_URL"
        else
            curl "${CURL_OPTS[@]}" -X POST "${HEADER_ARGS[@]}" "$TARGET_URL"
        fi
        ;;

    *)
        echo "Status: 405 Method Not Allowed"
        echo "Content-Type: text/html; charset=utf-8"
        echo ""
        echo "<script>alert('错误：不支持的请求方法 ${REQUEST_METHOD}，仅支持GET/POST！');history.back();</script>"
        exit 0
        ;;
esac

exit 0
