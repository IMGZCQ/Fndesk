#!/bin/sh

# 生成 HTML 响应
cat <<EOF
Content-Type: text/html

<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Fndesk 网络连接检测</title>
<style>
body {
font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
line-height: 1.6;
color: #333;
background-color: #f5f7fa;
margin: 0;
padding: 0;
}
.container {
max-width: 800px;
margin: 50px auto;
padding: 30px;
background-color: white;
border-radius: 8px;
box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}
h1 {
color: #2c3e50;
font-size: 28px;
margin-bottom: 20px;
text-align: center;
}
h2 {
color: #34495e;
font-size: 22px;
margin-top: 30px;
margin-bottom: 15px;
}
#status {
background-color: #e8f4f8;
border-left: 4px solid #3498db;
padding: 15px;
margin: 20px 0;
border-radius: 4px;
font-size: 16px;
min-height: 50px;
display: flex;
align-items: center;
}
.info {
color: #7f8c8d;
font-size: 14px;
text-align: center;
margin-top: 20px;
}
ul {
list-style-type: none;
padding: 0;
margin: 20px 0;
}
ul li {
margin: 10px 0;
}
a {
color: #3498db;
text-decoration: none;
font-size: 16px;
transition: all 0.3s ease;
display: inline-block;
padding: 8px 12px;
border: 1px solid #3498db;
border-radius: 4px;
background-color: white;
}
a:hover {
color: white;
background-color: #3498db;
text-decoration: none;
transform: translateY(-1px);
box-shadow: 0 2px 5px rgba(52, 152, 219, 0.3);
}
@keyframes pulse {
0% { opacity: 1; }
50% { opacity: 0.5; }
100% { opacity: 1; }
}
.loading {
animation: pulse 1.5s infinite;
}
</style>
<script>
function getQueryParams() {
var params = {};
var queryString = window.location.search;
if (!queryString || queryString === '?') {
return params;
}
queryString = queryString.substring(1);
var paramPairs = queryString.split(/&/g);
for (var i = 0; i < paramPairs.length; i++) {
var paramPair = paramPairs[i];
if (paramPair) {
var equalsIndex = paramPair.indexOf('=');
if (equalsIndex >= 0) {
var key = decodeURIComponent(paramPair.substring(0, equalsIndex).trim());
var value = decodeURIComponent(paramPair.substring(equalsIndex + 1).trim());
params[key] = value;
}
}
}
return params;
}
function buildUrls() {
var params = getQueryParams();
var urls = [];
var currentHostname = window.location.hostname;
var currentHost = window.location.host;
var targetIndexes = [1, 2];
var ipRegex = /^(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(.*?)(?::\d+)?$/;
for (var j = 0; j < targetIndexes.length; j++) {
var i = targetIndexes[j];
var uHKey = 'uH' + i;
var uBKey = 'uB' + i;
if (params[uHKey] && params[uBKey]) {
var uHValue = params[uHKey];
var uBValue = params[uBKey];
var url;
var pureProtocol = uHValue.replace(/:\/\//g, '').replace(/:/g, '').toLowerCase();
var protocol = (pureProtocol === 'https' || pureProtocol === 'http') ? pureProtocol : 'http';
if (/^\d/.test(uBValue)) {
if (ipRegex.test(uBValue)) {
url = protocol + '://' + uBValue;
}
else {
url = protocol + '://' + currentHostname + ':' + uBValue;
}
} else if (uBValue.indexOf('/') === 0) {
url = protocol + '://' + currentHost + uBValue;
} else {
url = protocol + '://' + uBValue;
}
urls.push(url);
}
}
return urls;
}
function checkUrlAccessibility(url, timeout) {
timeout = timeout || 2000;
var startTime = new Date().getTime();
console.log('开始可达性测试:', url, '超时设置:', timeout, 'ms');
function isInternalIp(url) {
var ipPattern = /\b(?:10|127|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b/;
return ipPattern.test(url);
}
return new Promise(function(resolve) {
var img = new Image();
img.crossOrigin = 'anonymous';
var completed = false;
var timeoutId = setTimeout(function() {
if (!completed) {
completed = true;
console.log('超时:', url, '(' + (new Date().getTime() - startTime) + 'ms)');
resolve(false);
}
}, timeout);
img.onload = function() {
if (!completed) {
completed = true;
clearTimeout(timeoutId);
console.log('可达:', url, '(' + (new Date().getTime() - startTime) + 'ms)');
resolve(true);
}
};
img.onerror = function() {
if (!completed) {
completed = true;
clearTimeout(timeoutId);
if (isInternalIp(url)) {
console.log('内网资源可能可达(跨域/SSL):', url);
resolve(true);
} else {
console.log('不可达:', url, '(' + (new Date().getTime() - startTime) + 'ms)');
resolve(false);
}
}
};
try {
var separator = url.indexOf('?') >= 0 ? '&' : '?';
img.src = url + separator + 'ping=' + new Date().getTime();
} catch (error) {
if (!completed) {
completed = true;
clearTimeout(timeoutId);
console.log('URL 格式错误:', url, error.message);
resolve(false);
}
}
});
}
function checkAndRedirect(prebuiltUrls) {
console.log('开始检测 URL...');
var urls = Array.isArray(prebuiltUrls) ? prebuiltUrls : buildUrls();
var statusElement = document.getElementById('status');
console.log('解析到的 URL 列表:', urls);
if (urls.length === 0) {
statusElement.innerHTML = '没有检测到有效的 URL 参数';
return;
}
if (urls.length === 1) {
statusElement.innerHTML = '检测到单个 URL，正在直接跳转：' + urls[0];
console.log('单个 URL，直接跳转:', urls[0]);
window.location.href = urls[0];
return;
}
var firstUrl = urls[0];
var secondUrl = urls[1];
statusElement.innerHTML = '正在检测第一个 URL：' + firstUrl;
console.log('开始检测第一个 URL:', firstUrl);
checkUrlAccessibility(firstUrl, 1000)
.then(function(accessible) {
console.log('第一个 URL 检测结果:', firstUrl, accessible);
if (accessible) {
statusElement.innerHTML = '第一个 URL 可达，正在跳转：' + firstUrl;
window.location.href = firstUrl;
} else {
statusElement.innerHTML = '第一个 URL 不可达，正在直接跳转第二个 URL：' + secondUrl;
console.log('第一个 URL 不可达，直接跳转第二个 URL:', secondUrl);
window.location.href = secondUrl;
}
})
.catch(function(error) {
console.log('第一个 URL 检测异常:', firstUrl, error);
statusElement.innerHTML = '第一个 URL 检测异常，正在直接跳转第二个 URL：' + secondUrl;
window.location.href = secondUrl;
});
}
var earlyUrls = buildUrls();
if (earlyUrls.length === 1) {
window.location.replace(earlyUrls[0]);
} else {
window.onload = function() { checkAndRedirect(earlyUrls); };
}
</script>
</head>
<body>
<div class="container">
<h1>正在检测可访问的 URL...</h1>
<p id="status" class="loading">准备开始检测...</p>
<p class="info">如果检测到可访问的 URL，将自动跳转...</p>
</div>
</body>
</html>
EOF