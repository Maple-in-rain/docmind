/* API 相对于应用入口解析，兼容根路径与 /docmind/ 共站部署。 */
function apiUrl(path, pageUrl = window.location.href) {
  return new URL(path.replace(/^\/+/, ""), new URL(".", pageUrl)).href;
}
