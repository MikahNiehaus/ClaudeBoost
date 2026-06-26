<!-- Source: https://docs.aiohttp.org/en/stable/web_reference.html | Tier: A | Topic: aiohttp-security | Fetched: 2026-06-26 -->

# Server Reference¶

## Request and Base Request¶

The Request object contains all the information about an incoming HTTP request.

`BaseRequest` is used for [Low-Level Servers](web_lowlevel.html#aiohttp-web-lowlevel) (which have no applications, routers, signals and middlewares). `Request` has an `Request.app` and `Request.match_info` attributes.

A `BaseRequest` / `Request` are [`dict`](https://docs.python.org/3/library/stdtypes.html#dict "\(in Python v3.14\)") like objects, allowing them to be used for [sharing data](web_advanced.html#aiohttp-web-data-sharing) among [Middlewares](web_advanced.html#aiohttp-web-middlewares) and [Signals](web_advanced.html#aiohttp-web-signals) handlers.

class aiohttp.web.BaseRequest[[source]](_modules/aiohttp/web_request.html#BaseRequest)¶
    

version¶
    

_HTTP version_ of request, Read-only property.

Returns `aiohttp.protocol.HttpVersion` instance.

method¶
    

_HTTP method_ , read-only property.

The value is upper-cased [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") like `"GET"`, `"POST"`, `"PUT"` etc.

url¶
    

A [`URL`](https://yarl.aio-libs.org/en/stable/api/#yarl.URL "\(in yarl v1.24\)") instance with absolute URL to resource (_scheme_ , _host_ and _port_ are included).

Note

In case of malformed request (e.g. without `"HOST"` HTTP header) the absolute url may be unavailable.

rel_url¶
    

A [`URL`](https://yarl.aio-libs.org/en/stable/api/#yarl.URL "\(in yarl v1.24\)") instance with relative URL to resource (contains _path_ , _query_ and _fragment_ parts only, _scheme_ , _host_ and _port_ are excluded).

The property is equal to `.url.relative()` but is always present.

See also

A note from `url`.

scheme¶
    

A string representing the scheme of the request.

The scheme is `'https'` if transport for request handling is _SSL_ , `'http'` otherwise.

The value could be overridden by `clone()`.

Read-only [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") property.

Changed in version 2.3: _Forwarded_ and _X-Forwarded-Proto_ are not used anymore.

Call `.clone(scheme=new_scheme)` for setting up the value explicitly.

See also

[Deploying behind a Proxy](web_advanced.html#aiohttp-web-forwarded-support)

secure¶
    

Shorthand for `request.url.scheme == 'https'`

Read-only [`bool`](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)") property.

See also

`scheme`

forwarded¶
    

A tuple containing all parsed Forwarded header(s).

Makes an effort to parse Forwarded headers as specified by [**RFC 7239**](https://datatracker.ietf.org/doc/html/rfc7239.html):

  * It adds one (immutable) dictionary per Forwarded `field-value`, i.e. per proxy. The element corresponds to the data in the Forwarded `field-value` added by the first proxy encountered by the client. Each subsequent item corresponds to those added by later proxies.

  * It checks that every value has valid syntax in general as specified in [**RFC 7239 Section 4**](https://datatracker.ietf.org/doc/html/rfc7239.html#section-4): either a `token` or a `quoted-string`.

  * It un-escapes `quoted-pairs`.

  * It does NOT validate ‘by’ and ‘for’ contents as specified in [**RFC 7239 Section 6**](https://datatracker.ietf.org/doc/html/rfc7239.html#section-6).

  * It does NOT validate `host` contents (Host ABNF).

  * It does NOT validate `proto` contents for valid URI scheme names.




Returns a tuple containing one or more `MappingProxy` objects

See also

`scheme`

See also

`host`

host¶
    

Host name of the request, resolved in this order:

  * Overridden value by `clone()` call.

  * _Host_ HTTP header

  * local socket address the request arrived on (transport `sockname`)

  * empty string if no transport information is available




Read-only [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") property.

Changed in version 2.3: _Forwarded_ and _X-Forwarded-Host_ are not used anymore.

Call `.clone(host=new_host)` for setting up the value explicitly.

Changed in version 3.13: The fallback when no `Host` header is present no longer calls [`socket.getfqdn()`](https://docs.python.org/3/library/socket.html#socket.getfqdn "\(in Python v3.14\)"), which performed blocking reverse-DNS resolution on the event loop. The local socket address (transport `sockname`) is used instead.

See also

[Deploying behind a Proxy](web_advanced.html#aiohttp-web-forwarded-support)

remote¶
    

Originating IP address of a client initiated HTTP request.

The IP is resolved through the following headers, in this order:

  * Overridden value by `clone()` call.

  * Peer name of opened socket.




Read-only [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") property.

Call `.clone(remote=new_remote)` for setting up the value explicitly.

Added in version 2.3.

See also

[Deploying behind a Proxy](web_advanced.html#aiohttp-web-forwarded-support)

client_max_size¶
    

The maximum size of the request body.

The value could be overridden by `clone()`.

Read-only [`int`](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)") property.

path_qs¶
    

The URL including PATH_INFO and the query string. e.g., `/app/blog?id=10`

Read-only [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") property.

path¶
    

The URL including _PATH INFO_ without the host or scheme. e.g., `/app/blog`. The path is URL-decoded. For raw path info see `raw_path`.

Read-only [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") property.

raw_path¶
    

The URL including raw _PATH INFO_ without the host or scheme. Warning, the path may be URL-encoded and may contain invalid URL characters, e.g. `/my%2Fpath%7Cwith%21some%25strange%24characters`.

For URL-decoded version please take a look on `path`.

Read-only [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") property.

query¶
    

A multidict with all the variables in the query string.

Read-only [`MultiDictProxy`](https://multidict.aio-libs.org/en/stable/multidict/#multidict.MultiDictProxy "\(in multidict v6.7\)") lazy property.

query_string¶
    

The query string in the URL, e.g., `id=10`

Read-only [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") property.

headers¶
    

A case-insensitive multidict proxy with all headers.

Read-only [`CIMultiDictProxy`](https://multidict.aio-libs.org/en/stable/multidict/#multidict.CIMultiDictProxy "\(in multidict v6.7\)") property.

raw_headers¶
    

HTTP headers of response as unconverted bytes, a sequence of `(key, value)` pairs.

keep_alive¶
    

`True` if keep-alive connection enabled by HTTP client and protocol version supports it, otherwise `False`.

Read-only [`bool`](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)") property.

transport¶
    

A [transport](https://docs.python.org/3/library/asyncio-protocol.html#asyncio-transport "\(in Python v3.14\)") used to process request. Read-only property.

The property can be used, for example, for getting IP address of client’s peer:
    
    
    peername = request.transport.get_extra_info('peername')
    if peername is not None:
        host, port = peername
    

loop¶
    

An event loop instance used by HTTP request handling.

Read-only [`asyncio.AbstractEventLoop`](https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.AbstractEventLoop "\(in Python v3.14\)") property.

Deprecated since version 3.5.

cookies¶
    

A read-only dictionary-like object containing the request’s cookies.

Read-only [`MappingProxyType`](https://docs.python.org/3/library/types.html#types.MappingProxyType "\(in Python v3.14\)") property.

content¶
    

A [`StreamReader`](streams.html#aiohttp.StreamReader "aiohttp.StreamReader") instance, input stream for reading request’s _BODY_.

Read-only property.

body_exists¶
    

Return `True` if request has _HTTP BODY_ , `False` otherwise.

Read-only [`bool`](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)") property.

Added in version 2.3.

can_read_body¶
    

Return `True` if request’s _HTTP BODY_ can be read, `False` otherwise.

Read-only [`bool`](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)") property.

Added in version 2.3.

has_body¶
    

Return `True` if request’s _HTTP BODY_ can be read, `False` otherwise.

Read-only [`bool`](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)") property.

Deprecated since version 2.3: Use `can_read_body()` instead.

content_type¶
    

Read-only property with _content_ part of _Content-Type_ header.

Returns [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") like `'text/html'`

Note

Returns value is `'application/octet-stream'` if no Content-Type header present in HTTP headers according to [**RFC 2616**](https://datatracker.ietf.org/doc/html/rfc2616.html)

charset¶
    

Read-only property that specifies the _encoding_ for the request’s BODY.

The value is parsed from the _Content-Type_ HTTP header.

Returns [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") like `'utf-8'` or `None` if _Content-Type_ has no charset information.

content_length¶
    

Read-only property that returns length of the request’s BODY.

The value is parsed from the _Content-Length_ HTTP header.

Returns [`int`](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)") or `None` if _Content-Length_ is absent.

http_range¶
    

Read-only property that returns information about _Range_ HTTP header.

Returns a [`slice`](https://docs.python.org/3/library/functions.html#slice "\(in Python v3.14\)") where `.start` is _left inclusive bound_ , `.stop` is _right exclusive bound_ and `.step` is `1`.

The property might be used in two manners:

  1. Attribute-access style (example assumes that both left and right borders are set, the real logic for case of open bounds is more complex):
         
         rng = request.http_range
         with open(filename, 'rb') as f:
             f.seek(rng.start)
             return f.read(rng.stop-rng.start)
         

  2. Slice-style:
         
         return buffer[request.http_range]
         




if_modified_since¶
    

Read-only property that returns the date specified in the _If-Modified-Since_ header.

Returns [`datetime.datetime`](https://docs.python.org/3/library/datetime.html#datetime.datetime "\(in Python v3.14\)") or `None` if _If-Modified-Since_ header is absent or is not a valid HTTP date.

if_unmodified_since¶
    

Read-only property that returns the date specified in the _If-Unmodified-Since_ header.

Returns [`datetime.datetime`](https://docs.python.org/3/library/datetime.html#datetime.datetime "\(in Python v3.14\)") or `None` if _If-Unmodified-Since_ header is absent or is not a valid HTTP date.

Added in version 3.1.

if_match¶
    

Read-only property that returns [`ETag`](client_reference.html#aiohttp.ETag "aiohttp.ETag") objects specified in the _If-Match_ header.

Returns [`tuple`](https://docs.python.org/3/library/stdtypes.html#tuple "\(in Python v3.14\)") of [`ETag`](client_reference.html#aiohttp.ETag "aiohttp.ETag") or `None` if _If-Match_ header is absent.

Added in version 3.8.

if_none_match¶
    

Read-only property that returns [`ETag`](client_reference.html#aiohttp.ETag "aiohttp.ETag") objects specified _If-None-Match_ header.

Returns [`tuple`](https://docs.python.org/3/library/stdtypes.html#tuple "\(in Python v3.14\)") of [`ETag`](client_reference.html#aiohttp.ETag "aiohttp.ETag") or `None` if _If-None-Match_ header is absent.

Added in version 3.8.

if_range¶
    

Read-only property that returns the date specified in the _If-Range_ header.

Returns [`datetime.datetime`](https://docs.python.org/3/library/datetime.html#datetime.datetime "\(in Python v3.14\)") or `None` if _If-Range_ header is absent or is not a valid HTTP date.

Added in version 3.1.

clone(_*_ , _method =..._, _rel_url =..._, _headers =..._)[[source]](_modules/aiohttp/web_request.html#BaseRequest.clone)¶
    

Clone itself with replacement some attributes.

Creates and returns a new instance of Request object. If no parameters are given, an exact copy is returned. If a parameter is not passed, it will reuse the one from the current request object.

Parameters:
    

  * **method** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – http method

  * **rel_url** – url to use, [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") or [`URL`](https://yarl.aio-libs.org/en/stable/api/#yarl.URL "\(in yarl v1.24\)")

  * **headers** – [`CIMultiDict`](https://multidict.aio-libs.org/en/stable/multidict/#multidict.CIMultiDict "\(in multidict v6.7\)") or compatible headers container.



Returns:
    

a cloned `Request` instance.

get_extra_info(_name_ , _default =None_)[[source]](_modules/aiohttp/web_request.html#BaseRequest.get_extra_info)¶
    

Reads extra information from the protocol’s transport. If no value associated with `name` is found, `default` is returned.

See [`asyncio.BaseTransport.get_extra_info()`](https://docs.python.org/3/library/asyncio-protocol.html#asyncio.BaseTransport.get_extra_info "\(in Python v3.14\)")

Parameters:
    

  * **name** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – The key to look up in the transport extra information.

  * **default** – Default value to be used when no value for `name` is found (default is `None`).




Added in version 3.7.

async read()[[source]](_modules/aiohttp/web_request.html#BaseRequest.read)¶
    

Read request body, returns [`bytes`](https://docs.python.org/3/library/stdtypes.html#bytes "\(in Python v3.14\)") object with body content.

Note

The method **does** store read data internally, subsequent `read()` call will return the same value.

async text()[[source]](_modules/aiohttp/web_request.html#BaseRequest.text)¶
    

Read request body, decode it using `charset` encoding or `UTF-8` if no encoding was specified in _MIME-type_.

Returns [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") with body content.

Note

The method **does** store read data internally, subsequent `text()` call will return the same value.

async json(_*_ , _loads =json.loads_)[[source]](_modules/aiohttp/web_request.html#BaseRequest.json)¶
    

Read request body decoded as _json_.

The method is just a boilerplate [coroutine](https://docs.python.org/3/library/asyncio-task.html#coroutine "\(in Python v3.14\)") implemented as:
    
    
    async def json(self, *, loads=json.loads):
        body = await self.text()
        return loads(body)
    

Parameters:
    

**loads** ([_collections.abc.Callable_](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable "\(in Python v3.14\)")) – any [callable](glossary.html#term-callable) that accepts [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") and returns [`dict`](https://docs.python.org/3/library/stdtypes.html#dict "\(in Python v3.14\)") with parsed JSON ([`json.loads()`](https://docs.python.org/3/library/json.html#json.loads "\(in Python v3.14\)") by default).

Note

The method **does** store read data internally, subsequent `json()` call will return the same value.

async multipart()[[source]](_modules/aiohttp/web_request.html#BaseRequest.multipart)¶
    

Returns [`aiohttp.MultipartReader`](multipart_reference.html#aiohttp.MultipartReader "aiohttp.MultipartReader") which processes incoming _multipart_ request.

The method is just a boilerplate [coroutine](https://docs.python.org/3/library/asyncio-task.html#coroutine "\(in Python v3.14\)") implemented as:
    
    
    async def multipart(self, *, reader=aiohttp.multipart.MultipartReader):
        return reader(self.headers, self._payload)
    

This method is a coroutine for consistency with the else reader methods.

Warning

The method **does not** store read data internally. That means once you exhausts multipart reader, you cannot get the request payload one more time.

See also

[Working with Multipart](multipart.html#aiohttp-multipart)

Changed in version 3.4: Dropped _reader_ parameter.

async post()[[source]](_modules/aiohttp/web_request.html#BaseRequest.post)¶
    

A [coroutine](https://docs.python.org/3/library/asyncio-task.html#coroutine "\(in Python v3.14\)") that reads POST parameters from request body.

Returns [`MultiDictProxy`](https://multidict.aio-libs.org/en/stable/multidict/#multidict.MultiDictProxy "\(in multidict v6.7\)") instance filled with parsed data.

If `method` is not _POST_ , _PUT_ , _PATCH_ , _TRACE_ or _DELETE_ or `content_type` is not empty or _application/x-www-form-urlencoded_ or _multipart/form-data_ returns empty multidict.

Note

The method **does** store read data internally, subsequent `post()` call will return the same value.

async release()[[source]](_modules/aiohttp/web_request.html#BaseRequest.release)¶
    

Release request.

Eat unread part of HTTP BODY if present.

Note

User code may never call `release()`, all required work will be processed by [`aiohttp.web`](web.html#module-aiohttp.web "aiohttp.web") internal machinery.

class aiohttp.web.Request[[source]](_modules/aiohttp/web_request.html#Request)¶
    

A request used for receiving request’s information by _web handler_.

Every [handler](web_quickstart.html#aiohttp-web-handler) accepts a request instance as the first positional parameter.

The class in derived from `BaseRequest`, shares all parent’s attributes and methods but has a couple of additional properties:

match_info¶
    

Read-only property with [`AbstractMatchInfo`](abc.html#aiohttp.abc.AbstractMatchInfo "aiohttp.abc.AbstractMatchInfo") instance for result of route resolving.

Note

Exact type of property depends on used router. If `app.router` is `UrlDispatcher` the property contains `UrlMappingMatchInfo` instance.

app¶
    

An `Application` instance used to call [request handler](web_quickstart.html#aiohttp-web-handler), Read-only property.

config_dict¶
    

A [`aiohttp.ChainMapProxy`](structures.html#aiohttp.ChainMapProxy "aiohttp.ChainMapProxy") instance for mapping all properties from the current application returned by `app` property and all its parents.

See also

[Application’s config](web_advanced.html#aiohttp-web-data-sharing-app-config)

Added in version 3.2.

Note

You should never create the `Request` instance manually – [`aiohttp.web`](web.html#module-aiohttp.web "aiohttp.web") does it for you. But `clone()` may be used for cloning _modified_ request copy with changed _path_ , _method_ etc.

class aiohttp.web.RequestKey(_name_ , _t_)[[source]](_modules/aiohttp/helpers.html#RequestKey)¶
    

Keys for use in `Request`.

See `AppKey` for more details.

## Response classes¶

For now, [`aiohttp.web`](web.html#module-aiohttp.web "aiohttp.web") has three classes for the _HTTP response_ : `StreamResponse`, `Response` and `FileResponse`.

Usually you need to use the second one. `StreamResponse` is intended for streaming data, while `Response` contains _HTTP BODY_ as an attribute and sends own content as single piece with the correct _Content-Length HTTP header_.

For sake of design decisions `Response` is derived from `StreamResponse` parent class.

The response supports _keep-alive_ handling out-of-the-box if _request_ supports it.

You can disable _keep-alive_ by `force_close()` though.

The common case for sending an answer from [web-handler](web_quickstart.html#aiohttp-web-handler) is returning a `Response` instance:
    
    
    async def handler(request):
        return Response(text="All right!")
    

Response classes are [`dict`](https://docs.python.org/3/library/stdtypes.html#dict "\(in Python v3.14\)") like objects, allowing them to be used for [sharing data](web_advanced.html#aiohttp-web-data-sharing) among [Middlewares](web_advanced.html#aiohttp-web-middlewares) and [Signals](web_advanced.html#aiohttp-web-signals) handlers:
    
    
    resp['key'] = value
    

Added in version 3.0: Dict-like interface support.

class aiohttp.web.StreamResponse(_*_ , _status =200_, _reason =None_)[[source]](_modules/aiohttp/web_response.html#StreamResponse)¶
    

The base class for the _HTTP response_ handling.

Contains methods for setting _HTTP response headers_ , _cookies_ , _response status code_ , writing _HTTP response BODY_ and so on.

The most important thing you should know about _response_ — it is _Finite State Machine_.

That means you can do any manipulations with _headers_ , _cookies_ and _status code_ only before `prepare()` coroutine is called.

Once you call `prepare()` any change of the _HTTP header_ part will raise [`RuntimeError`](https://docs.python.org/3/library/exceptions.html#RuntimeError "\(in Python v3.14\)") exception.

Any `write()` call after `write_eof()` is also forbidden.

Parameters:
    

  * **status** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – HTTP status code, `200` by default.

  * **reason** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – HTTP reason. If param is `None` reason will be calculated basing on _status_ parameter. Otherwise pass [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") with arbitrary _status_ explanation..




prepared¶
    

Read-only [`bool`](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)") property, `True` if `prepare()` has been called, `False` otherwise.

task¶
    

A task that serves HTTP request handling.

May be useful for graceful shutdown of long-running requests (streaming, long polling or web-socket).

status¶
    

Read-only property for _HTTP response status code_ , [`int`](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)").

`200` (OK) by default.

reason¶
    

Read-only property for _HTTP response reason_ , [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)").

set_status(_status_ , _reason =None_)[[source]](_modules/aiohttp/web_response.html#StreamResponse.set_status)¶
    

Set `status` and `reason`.

_reason_ value is auto calculated if not specified (`None`).

keep_alive¶
    

Read-only property, copy of `aiohttp.web.BaseRequest.keep_alive` by default.

Can be switched to `False` by `force_close()` call.

force_close()[[source]](_modules/aiohttp/web_response.html#StreamResponse.force_close)¶
    

Disable `keep_alive` for connection. There are no ways to enable it back.

compression¶
    

Read-only [`bool`](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)") property, `True` if compression is enabled.

`False` by default.

See also

`enable_compression()`

enable_compression(_force =None_, _strategy =None_)[[source]](_modules/aiohttp/web_response.html#StreamResponse.enable_compression)¶
    

Enable compression.

When _force_ is unset compression encoding is selected based on the request’s _Accept-Encoding_ header.

_Accept-Encoding_ is not checked if _force_ is set to a `ContentCoding`.

_strategy_ accepts a [`zlib`](https://docs.python.org/3/library/zlib.html#module-zlib "\(in Python v3.14\)") compression strategy. See [`zlib.compressobj()`](https://docs.python.org/3/library/zlib.html#zlib.compressobj "\(in Python v3.14\)") for possible values, or refer to the docs for the zlib of your using, should you use [`aiohttp.set_zlib_backend()`](client_reference.html#aiohttp.set_zlib_backend "aiohttp.set_zlib_backend") to change zlib backend. If `None`, the default value adopted by your zlib backend will be used where applicable.

See also

`compression`

chunked¶
    

Read-only property, indicates if chunked encoding is on.

Can be enabled by `enable_chunked_encoding()` call.

See also

`enable_chunked_encoding`

enable_chunked_encoding()[[source]](_modules/aiohttp/web_response.html#StreamResponse.enable_chunked_encoding)¶
    

Enables `chunked` encoding for response. There are no ways to disable it back. With enabled `chunked` encoding each `write()` operation encoded in separate chunk.

Warning

chunked encoding can be enabled for `HTTP/1.1` only.

Setting up both `content_length` and chunked encoding is mutually exclusive.

See also

`chunked`

headers¶
    

[`CIMultiDict`](https://multidict.aio-libs.org/en/stable/multidict/#multidict.CIMultiDict "\(in multidict v6.7\)") instance for _outgoing_ _HTTP headers_.

cookies¶
    

An instance of [`http.cookies.SimpleCookie`](https://docs.python.org/3/library/http.cookies.html#http.cookies.SimpleCookie "\(in Python v3.14\)") for _outgoing_ cookies.

Warning

Direct setting up _Set-Cookie_ header may be overwritten by explicit calls to cookie manipulation.

We are encourage using of `cookies` and `set_cookie()`, `del_cookie()` for cookie manipulations.

set_cookie(_name_ , _value_ , _*_ , _path ='/'_, _expires =None_, _domain =None_, _max_age =None_, _secure =None_, _httponly =None_, _version =None_, _samesite =None_, _partitioned =None_)[[source]](_modules/aiohttp/web_response.html#StreamResponse.set_cookie)¶
    

Convenient way for setting `cookies`, allows to specify some additional properties like _max_age_ in a single call.

Parameters:
    

  * **name** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – cookie name

  * **value** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – cookie value (will be converted to [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") if value has another type).

  * **expires** – expiration date (optional)

  * **domain** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – cookie domain (optional)

  * **max_age** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – defines the lifetime of the cookie, in seconds. The delta-seconds value is a decimal non- negative integer. After delta-seconds seconds elapse, the client should discard the cookie. A value of zero means the cookie should be discarded immediately. (optional)

  * **path** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – specifies the subset of URLs to which this cookie applies. (optional, `'/'` by default)

  * **secure** ([_bool_](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)")) – attribute (with no value) directs the user agent to use only (unspecified) secure means to contact the origin server whenever it sends back this cookie. The user agent (possibly under the user’s control) may determine what level of security it considers appropriate for “secure” cookies. The _secure_ should be considered security advice from the server to the user agent, indicating that it is in the session’s interest to protect the cookie contents. (optional)

  * **httponly** ([_bool_](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)")) – `True` if the cookie HTTP only (optional)

  * **version** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – a decimal integer, identifies to which version of the state management specification the cookie conforms. (optional)

  * **samesite** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – 

Asserts that a cookie must not be sent with cross-origin requests, providing some protection against cross-site request forgery attacks. Generally the value should be one of: `None`, `Lax` or `Strict`. (optional)

> Added in version 3.7.

  * **partitioned** ([_bool_](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)")) – 

`True` to set a partitioned cookie. Available in Python 3.14+. (optional)

> Added in version 3.12.




Warning

In HTTP version 1.1, `expires` was deprecated and replaced with the easier-to-use `max-age`, but Internet Explorer (IE6, IE7, and IE8) **does not** support `max-age`.

del_cookie(_name_ , _*_ , _path ='/'_, _domain =None_)[[source]](_modules/aiohttp/web_response.html#StreamResponse.del_cookie)¶
    

Deletes cookie.

Parameters:
    

  * **name** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – cookie name

  * **domain** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – optional cookie domain

  * **path** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – optional cookie path, `'/'` by default




content_length¶
    

_Content-Length_ for outgoing response.

content_type¶
    

_Content_ part of _Content-Type_ for outgoing response.

charset¶
    

_Charset_ aka _encoding_ part of _Content-Type_ for outgoing response.

The value converted to lower-case on attribute assigning.

last_modified¶
    

_Last-Modified_ header for outgoing response.

This property accepts raw [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") values, [`datetime.datetime`](https://docs.python.org/3/library/datetime.html#datetime.datetime "\(in Python v3.14\)") objects, Unix timestamps specified as an [`int`](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)") or a [`float`](https://docs.python.org/3/library/functions.html#float "\(in Python v3.14\)") object, and the value `None` to unset the header.

etag¶
    

_ETag_ header for outgoing response.

This property accepts raw [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") values, [`ETag`](client_reference.html#aiohttp.ETag "aiohttp.ETag") objects and the value `None` to unset the header.

In case of [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") input, etag is considered as strong by default.

**Do not** use double quotes `"` in the etag value, they will be added automatically.

Added in version 3.8.

async prepare(_request_)[[source]](_modules/aiohttp/web_response.html#StreamResponse.prepare)¶
    

Parameters:
    

**request** (_aiohttp.web.Request_) – HTTP request object, that the response answers.

Send _HTTP header_. You should not change any header data after calling this method.

The coroutine calls `on_response_prepare` signal handlers after default headers have been computed and directly before headers are sent.

async write(_data_)[[source]](_modules/aiohttp/web_response.html#StreamResponse.write)¶
    

Send byte-ish data as the part of _response BODY_ :
    
    
    await resp.write(data)
    

`prepare()` must be invoked before the call.

Raises [`TypeError`](https://docs.python.org/3/library/exceptions.html#TypeError "\(in Python v3.14\)") if data is not [`bytes`](https://docs.python.org/3/library/stdtypes.html#bytes "\(in Python v3.14\)"), [`bytearray`](https://docs.python.org/3/library/stdtypes.html#bytearray "\(in Python v3.14\)") or [`memoryview`](https://docs.python.org/3/library/stdtypes.html#memoryview "\(in Python v3.14\)") instance.

Raises [`RuntimeError`](https://docs.python.org/3/library/exceptions.html#RuntimeError "\(in Python v3.14\)") if `prepare()` has not been called.

Raises [`RuntimeError`](https://docs.python.org/3/library/exceptions.html#RuntimeError "\(in Python v3.14\)") if `write_eof()` has been called.

async write_eof()[[source]](_modules/aiohttp/web_response.html#StreamResponse.write_eof)¶
    

A [coroutine](https://docs.python.org/3/library/asyncio-task.html#coroutine "\(in Python v3.14\)") _may_ be called as a mark of the _HTTP response_ processing finish.

_Internal machinery_ will call this method at the end of the request processing if needed.

After `write_eof()` call any manipulations with the _response_ object are forbidden.

class aiohttp.web.Response(_*_ , _body =None_, _status =200_, _reason =None_, _text =None_, _headers =None_, _content_type =None_, _charset =None_, _zlib_executor_size =sentinel_, _zlib_executor =None_)[[source]](_modules/aiohttp/web_response.html#Response)¶
    

The most usable response class, inherited from `StreamResponse`.

Accepts _body_ argument for setting the _HTTP response BODY_.

The actual `body` sending happens in overridden `write_eof()`.

Parameters:
    

  * **body** ([_bytes_](https://docs.python.org/3/library/stdtypes.html#bytes "\(in Python v3.14\)")) – response’s BODY

  * **status** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – HTTP status code, 200 OK by default.

  * **headers** ([_collections.abc.Mapping_](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping "\(in Python v3.14\)")) – HTTP headers that should be added to response’s ones.

  * **text** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – response’s BODY

  * **content_type** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – response’s content type. `'text/plain'` if _text_ is passed also, `'application/octet-stream'` otherwise.

  * **charset** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – response’s charset. `'utf-8'` if _text_ is passed also, `None` otherwise.

  * **zlib_executor_size** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – 

length in bytes which will trigger zlib compression
    

of body to happen in an executor

Added in version 3.5.

  * **zlib_executor** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – 

executor to use for zlib compression

Added in version 3.5.




body¶
    

Read-write attribute for storing response’s content aka BODY, [`bytes`](https://docs.python.org/3/library/stdtypes.html#bytes "\(in Python v3.14\)").

Assigning [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") to `body` will make the `body` type of `aiohttp.payload.StringPayload`, which tries to encode the given data based on _Content-Type_ HTTP header, while defaulting to `UTF-8`.

text¶
    

Read-write attribute for storing response’s `body`, represented as [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)").

class aiohttp.web.FileResponse(_*_ , _path_ , _chunk_size =256 * 1024_, _status =200_, _reason =None_, _headers =None_)[[source]](_modules/aiohttp/web_fileresponse.html#FileResponse)¶
    

The response class used to send files, inherited from `StreamResponse`.

Supports the `Content-Range` and `If-Range` HTTP Headers in requests.

The actual `body` sending happens in overridden `prepare()`.

Parameters:
    

  * **path** – Path to file. Accepts both [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") and [`pathlib.Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path "\(in Python v3.14\)").

  * **chunk_size** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – Chunk size in bytes which will be passed into [`io.RawIOBase.read()`](https://docs.python.org/3/library/io.html#io.RawIOBase.read "\(in Python v3.14\)") in the event that the `sendfile` system call is not supported.

  * **status** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – HTTP status code, `200` by default.

  * **reason** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – HTTP reason. If param is `None` reason will be calculated basing on _status_ parameter. Otherwise pass [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") with arbitrary _status_ explanation..

  * **headers** ([_collections.abc.Mapping_](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping "\(in Python v3.14\)")) – HTTP headers that should be added to response’s ones. The `Content-Type` response header will be overridden if provided.




class aiohttp.web.WebSocketResponse(_*_ , _timeout =10.0_, _receive_timeout =None_, _autoclose =True_, _autoping =True_, _heartbeat =None_, _protocols =()_, _compress =True_, _max_msg_size =4194304_, _writer_limit =65536_, _decode_text =True_)[[source]](_modules/aiohttp/web_ws.html#WebSocketResponse)¶
    

Class for handling server-side websockets, inherited from `StreamResponse`.

After starting (by `prepare()` call) the response you cannot use `write()` method but should to communicate with websocket client by `send_str()`, `receive()` and others.

To enable back-pressure from slow websocket clients treat methods `ping()`, `pong()`, `send_str()`, `send_bytes()`, `send_json()`, `send_frame()` as coroutines. By default write buffer size is set to 64k.

Parameters:
    

  * **autoping** ([_bool_](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)")) – Automatically send [`PONG`](websocket_utilities.html#aiohttp.WSMsgType.PONG "aiohttp.WSMsgType.PONG") on [`PING`](websocket_utilities.html#aiohttp.WSMsgType.PING "aiohttp.WSMsgType.PING") message from client, and handle [`PONG`](websocket_utilities.html#aiohttp.WSMsgType.PONG "aiohttp.WSMsgType.PONG") responses from client. Note that server does not send [`PING`](websocket_utilities.html#aiohttp.WSMsgType.PING "aiohttp.WSMsgType.PING") requests, you need to do this explicitly using `ping()` method.

  * **heartbeat** ([_float_](https://docs.python.org/3/library/functions.html#float "\(in Python v3.14\)")) – Send ping message every heartbeat seconds and wait pong response, close connection if pong response is not received. The timer is reset on any inbound data reception (coalesced per event loop iteration).

  * **timeout** ([_float_](https://docs.python.org/3/library/functions.html#float "\(in Python v3.14\)")) – Timeout value for the `close` operation. After sending the close websocket message, `close` waits for `timeout` seconds for a response. Default value is `10.0` (10 seconds for `close` operation)

  * **receive_timeout** ([_float_](https://docs.python.org/3/library/functions.html#float "\(in Python v3.14\)")) – Timeout value for receive operations. Default value is [`None`](https://docs.python.org/3/library/constants.html#None "\(in Python v3.14\)") (no timeout for receive operation)

  * **compress** ([_bool_](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)")) – Enable per-message deflate extension support. [`False`](https://docs.python.org/3/library/constants.html#False "\(in Python v3.14\)") for disabled, default value is [`True`](https://docs.python.org/3/library/constants.html#True "\(in Python v3.14\)").

  * **max_msg_size** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – 

maximum size of read websocket message, 4
    

MB by default. To disable the size limit use `0`.

Added in version 3.3.

  * **autoclose** ([_bool_](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)")) – Close connection when the client sends a [`CLOSE`](websocket_utilities.html#aiohttp.WSMsgType.CLOSE "aiohttp.WSMsgType.CLOSE") message, `True` by default. If set to `False`, the connection is not closed and the caller is responsible for calling `request.transport.close()` to avoid leaking resources.

  * **writer_limit** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – 

maximum size of write buffer, 64 KB by default.
    

Once the buffer is full, the websocket will pause to drain the buffer.

Added in version 3.11.

  * **decode_text** ([_bool_](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)")) – 

If `True` (default), TEXT messages are
    

decoded to strings. If `False`, TEXT messages are returned as raw bytes, which can improve performance when using JSON parsers like `orjson` that accept bytes directly.

Added in version 3.14.




The class supports `async for` statement for iterating over incoming messages:
    
    
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
        async for msg in ws:
            print(msg.data)
    

async prepare(_request_)[[source]](_modules/aiohttp/web_ws.html#WebSocketResponse.prepare)¶
    

Starts websocket. After the call you can use websocket methods.

Parameters:
    

**request** (_aiohttp.web.Request_) – HTTP request object, that the response answers.

Raises:
    

**HTTPException** – if websocket handshake has failed.

can_prepare(_request_)[[source]](_modules/aiohttp/web_ws.html#WebSocketResponse.can_prepare)¶
    

Performs checks for _request_ data to figure out if websocket can be started on the request.

If `can_prepare()` call is success then `prepare()` will success too.

Parameters:
    

**request** (_aiohttp.web.Request_) – HTTP request object, that the response answers.

Returns:
    

`WebSocketReady` instance.

`WebSocketReady.ok` is `True` on success, `WebSocketReady.protocol` is websocket subprotocol which is passed by client and accepted by server (one of _protocols_ sequence from `WebSocketResponse` ctor). `WebSocketReady.protocol` may be `None` if client and server subprotocols are not overlapping.

Note

The method never raises exception.

closed¶
    

Read-only property, `True` if connection has been closed or in process of closing. [`CLOSE`](websocket_utilities.html#aiohttp.WSMsgType.CLOSE "aiohttp.WSMsgType.CLOSE") message has been received from peer.

prepared¶
    

Read-only [`bool`](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)") property, `True` if `prepare()` has been called, `False` otherwise.

close_code¶
    

Read-only property, close code from peer. It is set to `None` on opened connection.

ws_protocol¶
    

Websocket _subprotocol_ chosen after `start()` call.

May be `None` if server and client protocols are not overlapping.

get_extra_info(_name_ , _default =None_)[[source]](_modules/aiohttp/web_ws.html#WebSocketResponse.get_extra_info)¶
    

Reads optional extra information from the writer’s transport. If no value associated with `name` is found, `default` is returned.

See [`asyncio.BaseTransport.get_extra_info()`](https://docs.python.org/3/library/asyncio-protocol.html#asyncio.BaseTransport.get_extra_info "\(in Python v3.14\)")

Parameters:
    

  * **name** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – The key to look up in the transport extra information.

  * **default** – Default value to be used when no value for `name` is found (default is `None`).




exception()[[source]](_modules/aiohttp/web_ws.html#WebSocketResponse.exception)¶
    

Returns last occurred exception or None.

async ping(_message =b''_)[[source]](_modules/aiohttp/web_ws.html#WebSocketResponse.ping)¶
    

Send [`PING`](websocket_utilities.html#aiohttp.WSMsgType.PING "aiohttp.WSMsgType.PING") to peer.

Parameters:
    

**message** – optional payload of _ping_ message, [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") (converted to _UTF-8_ encoded bytes) or [`bytes`](https://docs.python.org/3/library/stdtypes.html#bytes "\(in Python v3.14\)").

Raises:
    

  * [**RuntimeError**](https://docs.python.org/3/library/exceptions.html#RuntimeError "\(in Python v3.14\)") – if the connections is not started.

  * [**aiohttp.ClientConnectionResetError**](client_reference.html#aiohttp.ClientConnectionResetError "aiohttp.ClientConnectionResetError") – if the connection is closing.




Changed in version 3.0: The method is converted into [coroutine](https://docs.python.org/3/glossary.html#term-coroutine "\(in Python v3.14\)")

async pong(_message =b''_)[[source]](_modules/aiohttp/web_ws.html#WebSocketResponse.pong)¶
    

Send _unsolicited_ [`PONG`](websocket_utilities.html#aiohttp.WSMsgType.PONG "aiohttp.WSMsgType.PONG") to peer.

Parameters:
    

**message** – optional payload of _pong_ message, [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") (converted to _UTF-8_ encoded bytes) or [`bytes`](https://docs.python.org/3/library/stdtypes.html#bytes "\(in Python v3.14\)").

Raises:
    

  * [**RuntimeError**](https://docs.python.org/3/library/exceptions.html#RuntimeError "\(in Python v3.14\)") – if the connections is not started.

  * [**aiohttp.ClientConnectionResetError**](client_reference.html#aiohttp.ClientConnectionResetError "aiohttp.ClientConnectionResetError") – if the connection is closing.




Changed in version 3.0: The method is converted into [coroutine](https://docs.python.org/3/glossary.html#term-coroutine "\(in Python v3.14\)")

async send_str(_data_ , _compress =None_)[[source]](_modules/aiohttp/web_ws.html#WebSocketResponse.send_str)¶
    

Send _data_ to peer as [`TEXT`](websocket_utilities.html#aiohttp.WSMsgType.TEXT "aiohttp.WSMsgType.TEXT") message.

Parameters:
    

  * **data** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – data to send.

  * **compress** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – sets specific level of compression for single message, `None` for not overriding per-socket setting.



Raises:
    

  * [**RuntimeError**](https://docs.python.org/3/library/exceptions.html#RuntimeError "\(in Python v3.14\)") – if the connection is not started.

  * [**TypeError**](https://docs.python.org/3/library/exceptions.html#TypeError "\(in Python v3.14\)") – if data is not [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")

  * [**aiohttp.ClientConnectionResetError**](client_reference.html#aiohttp.ClientConnectionResetError "aiohttp.ClientConnectionResetError") – if the connection is closing.




Changed in version 3.0: The method is converted into [coroutine](https://docs.python.org/3/glossary.html#term-coroutine "\(in Python v3.14\)"), _compress_ parameter added.

async send_bytes(_data_ , _compress =None_)[[source]](_modules/aiohttp/web_ws.html#WebSocketResponse.send_bytes)¶
    

Send _data_ to peer as [`BINARY`](websocket_utilities.html#aiohttp.WSMsgType.BINARY "aiohttp.WSMsgType.BINARY") message.

Parameters:
    

  * **data** – data to send.

  * **compress** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – sets specific level of compression for single message, `None` for not overriding per-socket setting.



Raises:
    

  * [**RuntimeError**](https://docs.python.org/3/library/exceptions.html#RuntimeError "\(in Python v3.14\)") – if the connection is not started.

  * [**TypeError**](https://docs.python.org/3/library/exceptions.html#TypeError "\(in Python v3.14\)") – if data is not [`bytes`](https://docs.python.org/3/library/stdtypes.html#bytes "\(in Python v3.14\)"), [`bytearray`](https://docs.python.org/3/library/stdtypes.html#bytearray "\(in Python v3.14\)") or [`memoryview`](https://docs.python.org/3/library/stdtypes.html#memoryview "\(in Python v3.14\)").

  * [**aiohttp.ClientConnectionResetError**](client_reference.html#aiohttp.ClientConnectionResetError "aiohttp.ClientConnectionResetError") – if the connection is closing.




Changed in version 3.0: The method is converted into [coroutine](https://docs.python.org/3/glossary.html#term-coroutine "\(in Python v3.14\)"), _compress_ parameter added.

async send_json(_data_ , _compress =None_, _*_ , _dumps =json.dumps_)[[source]](_modules/aiohttp/web_ws.html#WebSocketResponse.send_json)¶
    

Send _data_ to peer as JSON string.

Parameters:
    

  * **data** – data to send.

  * **compress** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – sets specific level of compression for single message, `None` for not overriding per-socket setting.

  * **dumps** ([_collections.abc.Callable_](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable "\(in Python v3.14\)")) – any [callable](glossary.html#term-callable) that accepts an object and returns a JSON string ([`json.dumps()`](https://docs.python.org/3/library/json.html#json.dumps "\(in Python v3.14\)") by default).



Raises:
    

  * [**RuntimeError**](https://docs.python.org/3/library/exceptions.html#RuntimeError "\(in Python v3.14\)") – if the connection is not started.

  * [**ValueError**](https://docs.python.org/3/library/exceptions.html#ValueError "\(in Python v3.14\)") – if data is not serializable object

  * [**TypeError**](https://docs.python.org/3/library/exceptions.html#TypeError "\(in Python v3.14\)") – if value returned by `dumps` param is not [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")

  * [**aiohttp.ClientConnectionResetError**](client_reference.html#aiohttp.ClientConnectionResetError "aiohttp.ClientConnectionResetError") – if the connection is closing.




Changed in version 3.0: The method is converted into [coroutine](https://docs.python.org/3/glossary.html#term-coroutine "\(in Python v3.14\)"), _compress_ parameter added.

async send_json_bytes(_data_ , _compress =None_, _*_ , _dumps_)[[source]](_modules/aiohttp/web_ws.html#WebSocketResponse.send_json_bytes)¶
    

Send _data_ to peer as a JSON binary frame using a bytes-returning encoder.

Parameters:
    

  * **data** – data to send.

  * **compress** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – sets specific level of compression for single message, `None` for not overriding per-socket setting.

  * **dumps** ([_collections.abc.Callable_](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable "\(in Python v3.14\)")) – any [callable](glossary.html#term-callable) that accepts an object and returns JSON as [`bytes`](https://docs.python.org/3/library/stdtypes.html#bytes "\(in Python v3.14\)") (e.g. `orjson.dumps`).



Raises:
    

  * [**RuntimeError**](https://docs.python.org/3/library/exceptions.html#RuntimeError "\(in Python v3.14\)") – if the connection is not started.

  * [**ValueError**](https://docs.python.org/3/library/exceptions.html#ValueError "\(in Python v3.14\)") – if data is not serializable object

  * [**TypeError**](https://docs.python.org/3/library/exceptions.html#TypeError "\(in Python v3.14\)") – if value returned by `dumps` param is not [`bytes`](https://docs.python.org/3/library/stdtypes.html#bytes "\(in Python v3.14\)")




async send_frame(_message_ , _opcode_ , _compress =None_)[[source]](_modules/aiohttp/web_ws.html#WebSocketResponse.send_frame)¶
    

Send a [`WSMsgType`](websocket_utilities.html#aiohttp.WSMsgType "aiohttp.WSMsgType") message _message_ to peer.

This method is low-level and should be used with caution as it only accepts bytes which must conform to the correct message type for _message_.

It is recommended to use the `send_str()`, `send_bytes()` or `send_json()` methods instead of this method.

The primary use case for this method is to send bytes that are have already been encoded without having to decode and re-encode them.

Parameters:
    

  * **message** ([_bytes_](https://docs.python.org/3/library/stdtypes.html#bytes "\(in Python v3.14\)")) – message to send.

  * **opcode** ([_WSMsgType_](websocket_utilities.html#aiohttp.WSMsgType "aiohttp.WSMsgType")) – opcode of the message.

  * **compress** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – sets specific level of compression for single message, `None` for not overriding per-socket setting.



Raises:
    

  * [**RuntimeError**](https://docs.python.org/3/library/exceptions.html#RuntimeError "\(in Python v3.14\)") – if the connection is not started.

  * [**aiohttp.ClientConnectionResetError**](client_reference.html#aiohttp.ClientConnectionResetError "aiohttp.ClientConnectionResetError") – if the connection is closing.




Added in version 3.11.

async close(_*_ , _code =WSCloseCode.OK_, _message =b''_, _drain =True_)[[source]](_modules/aiohttp/web_ws.html#WebSocketResponse.close)¶
    

A [coroutine](https://docs.python.org/3/library/asyncio-task.html#coroutine "\(in Python v3.14\)") that initiates closing handshake by sending [`CLOSE`](websocket_utilities.html#aiohttp.WSMsgType.CLOSE "aiohttp.WSMsgType.CLOSE") message.

It is safe to call close() from different task.

Parameters:
    

  * **code** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – closing code. See also [`WSCloseCode`](websocket_utilities.html#aiohttp.WSCloseCode "aiohttp.WSCloseCode").

  * **message** – optional payload of _close_ message, [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") (converted to _UTF-8_ encoded bytes) or [`bytes`](https://docs.python.org/3/library/stdtypes.html#bytes "\(in Python v3.14\)").

  * **drain** ([_bool_](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)")) – drain outgoing buffer before closing connection.



Raises:
    

[**RuntimeError**](https://docs.python.org/3/library/exceptions.html#RuntimeError "\(in Python v3.14\)") – if connection is not started

async receive(_timeout =None_)[[source]](_modules/aiohttp/web_ws.html#WebSocketResponse.receive)¶
    

A [coroutine](https://docs.python.org/3/library/asyncio-task.html#coroutine "\(in Python v3.14\)") that waits upcoming _data_ message from peer and returns it.

The coroutine implicitly handles [`PING`](websocket_utilities.html#aiohttp.WSMsgType.PING "aiohttp.WSMsgType.PING"), [`PONG`](websocket_utilities.html#aiohttp.WSMsgType.PONG "aiohttp.WSMsgType.PONG") and [`CLOSE`](websocket_utilities.html#aiohttp.WSMsgType.CLOSE "aiohttp.WSMsgType.CLOSE") without returning the message.

It process _ping-pong game_ and performs _closing handshake_ internally.

Note

Can only be called by the request handling task.

Parameters:
    

**timeout** – 

timeout for receive operation.

timeout value overrides response`s receive_timeout attribute.

Returns:
    

[`WSMessage`](websocket_utilities.html#aiohttp.WSMessage "aiohttp.WSMessage")

Raises:
    

  * [**RuntimeError**](https://docs.python.org/3/library/exceptions.html#RuntimeError "\(in Python v3.14\)") – if connection is not started

  * [**asyncio.TimeoutError**](https://docs.python.org/3/library/asyncio-exceptions.html#asyncio.TimeoutError "\(in Python v3.14\)") – if timeout expires before receiving a message




async receive_str(_*_ , _timeout =None_)[[source]](_modules/aiohttp/web_ws.html#WebSocketResponse.receive_str)¶
    

A [coroutine](https://docs.python.org/3/library/asyncio-task.html#coroutine "\(in Python v3.14\)") that calls `receive()` but also asserts the message type is [`TEXT`](websocket_utilities.html#aiohttp.WSMsgType.TEXT "aiohttp.WSMsgType.TEXT").

Note

Can only be called by the request handling task.

Parameters:
    

**timeout** – 

timeout for receive operation.

timeout value overrides response`s receive_timeout attribute.

Return str:
    

peer’s message content.

Raises:
    

  * [**aiohttp.WSMessageTypeError**](client_reference.html#aiohttp.WSMessageTypeError "aiohttp.WSMessageTypeError") – if message is not [`TEXT`](websocket_utilities.html#aiohttp.WSMsgType.TEXT "aiohttp.WSMsgType.TEXT").

  * [**asyncio.TimeoutError**](https://docs.python.org/3/library/asyncio-exceptions.html#asyncio.TimeoutError "\(in Python v3.14\)") – if timeout expires before receiving a message




async receive_bytes(_*_ , _timeout =None_)[[source]](_modules/aiohttp/web_ws.html#WebSocketResponse.receive_bytes)¶
    

A [coroutine](https://docs.python.org/3/library/asyncio-task.html#coroutine "\(in Python v3.14\)") that calls `receive()` but also asserts the message type is [`BINARY`](websocket_utilities.html#aiohttp.WSMsgType.BINARY "aiohttp.WSMsgType.BINARY").

Note

Can only be called by the request handling task.

Parameters:
    

**timeout** – 

timeout for receive operation.

timeout value overrides response`s receive_timeout attribute.

Return bytes:
    

peer’s message content.

Raises:
    

  * [**aiohttp.WSMessageTypeError**](client_reference.html#aiohttp.WSMessageTypeError "aiohttp.WSMessageTypeError") – if message is not [`BINARY`](websocket_utilities.html#aiohttp.WSMsgType.BINARY "aiohttp.WSMsgType.BINARY").

  * [**asyncio.TimeoutError**](https://docs.python.org/3/library/asyncio-exceptions.html#asyncio.TimeoutError "\(in Python v3.14\)") – if timeout expires before receiving a message




async receive_json(_*_ , _loads =json.loads_, _timeout =None_)[[source]](_modules/aiohttp/web_ws.html#WebSocketResponse.receive_json)¶
    

A [coroutine](https://docs.python.org/3/library/asyncio-task.html#coroutine "\(in Python v3.14\)") that calls `receive_str()` and loads the JSON string to a Python dict.

Note

Can only be called by the request handling task.

Parameters:
    

  * **loads** ([_collections.abc.Callable_](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable "\(in Python v3.14\)")) – any [callable](glossary.html#term-callable) that accepts [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") and returns [`dict`](https://docs.python.org/3/library/stdtypes.html#dict "\(in Python v3.14\)") with parsed JSON ([`json.loads()`](https://docs.python.org/3/library/json.html#json.loads "\(in Python v3.14\)") by default).

  * **timeout** – 

timeout for receive operation.

timeout value overrides response`s receive_timeout attribute.



Return dict:
    

loaded JSON content

Raises:
    

  * [**TypeError**](https://docs.python.org/3/library/exceptions.html#TypeError "\(in Python v3.14\)") – if message is [`BINARY`](websocket_utilities.html#aiohttp.WSMsgType.BINARY "aiohttp.WSMsgType.BINARY").

  * [**ValueError**](https://docs.python.org/3/library/exceptions.html#ValueError "\(in Python v3.14\)") – if message is not valid JSON.

  * [**asyncio.TimeoutError**](https://docs.python.org/3/library/asyncio-exceptions.html#asyncio.TimeoutError "\(in Python v3.14\)") – if timeout expires before receiving a message




See also

[WebSockets handling](web_quickstart.html#aiohttp-web-websockets)

class aiohttp.web.WebSocketReady[[source]](_modules/aiohttp/web_ws.html#WebSocketReady)¶
    

A named tuple for returning result from `WebSocketResponse.can_prepare()`.

Has [`bool`](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)") check implemented, e.g.:
    
    
    if not await ws.can_prepare(...):
        cannot_start_websocket()
    

ok¶
    

`True` if websocket connection can be established, `False` otherwise.

protocol¶
    

[`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") represented selected websocket sub-protocol.

See also

`WebSocketResponse.can_prepare()`

aiohttp.web.json_response([_data_ , ]_*_ , _text =None_, _body =None_, _status =200_, _reason =None_, _headers =None_, _content_type ='application/json'_, _dumps =json.dumps_)[[source]](_modules/aiohttp/web_response.html#json_response)¶
    

Return `Response` with predefined `'application/json'` content type and _data_ encoded by `dumps` parameter ([`json.dumps()`](https://docs.python.org/3/library/json.html#json.dumps "\(in Python v3.14\)") by default).

### HTTP Exceptions¶

Errors can also be returned by raising a HTTP exception instance from within the handler.

class aiohttp.web.HTTPException(_*_ , _headers =None_, _reason =None_, _text =None_, _content_type =None_)[[source]](_modules/aiohttp/web_exceptions.html#HTTPException)¶
    

Low-level HTTP failure.

Parameters:
    

  * **headers** ([_dict_](https://docs.python.org/3/library/stdtypes.html#dict "\(in Python v3.14\)") _or_[ _multidict.CIMultiDict_](https://multidict.aio-libs.org/en/stable/multidict/#multidict.CIMultiDict "\(in multidict v6.7\)")) – headers for the response

  * **reason** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – reason included in the response

  * **text** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – response’s body

  * **content_type** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – response’s content type. This is passed through to the `Response` initializer.




Sub-classes of `HTTPException` exist for the standard HTTP response codes as described in [Exceptions](web_quickstart.html#aiohttp-web-exceptions) and the expected usage is to simply raise the appropriate exception type to respond with a specific HTTP response code.

Since `HTTPException` is a sub-class of `Response`, it contains the methods and properties that allow you to directly manipulate details of the response.

status_code¶
    

HTTP status code for this exception class. This attribute is usually defined at the class level. `self.status_code` is passed to the `Response` initializer.

aiohttp.web.json_bytes_response([_data_ , ]_*_ , _dumps_ , _body =None_, _status =200_, _reason =None_, _headers =None_, _content_type ='application/json'_)[[source]](_modules/aiohttp/web_response.html#json_bytes_response)¶
    

Return `Response` with predefined `'application/json'` content type and _data_ encoded by `dumps` parameter which must return [`bytes`](https://docs.python.org/3/library/stdtypes.html#bytes "\(in Python v3.14\)") directly (e.g. `orjson.dumps`).

Use this when your JSON encoder returns [`bytes`](https://docs.python.org/3/library/stdtypes.html#bytes "\(in Python v3.14\)") instead of [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)"), avoiding the [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")-to-[`bytes`](https://docs.python.org/3/library/stdtypes.html#bytes "\(in Python v3.14\)") encoding overhead.

class aiohttp.web.ResponseKey(_name_ , _t_)[[source]](_modules/aiohttp/helpers.html#ResponseKey)¶
    

Keys for use in `Response`.

See `AppKey` for more details.

## Application and Router¶

class aiohttp.web.Application(_*_ , _logger =<default>_, _router =None_, _middlewares =()_, _handler_args =None_, _client_max_size =1024**2_, _loop =None_, _debug =..._)[[source]](_modules/aiohttp/web_app.html#Application)¶
    

Application is a synonym for web-server.

To get a fully working example, you have to make an _application_ , register supported urls in the _router_ and pass it to `aiohttp.web.run_app()` or `aiohttp.web.AppRunner`.

_Application_ contains a _router_ instance and a list of callbacks that will be called during application finishing.

This class is a [`dict`](https://docs.python.org/3/library/stdtypes.html#dict "\(in Python v3.14\)")-like object, so you can use it for [sharing data](web_advanced.html#aiohttp-web-data-sharing) globally by storing arbitrary properties for later access from a [handler](web_quickstart.html#aiohttp-web-handler) via the `Request.app` property:
    
    
    app = Application()
    database = AppKey("database", AsyncEngine)
    app[database] = await create_async_engine(db_url)
    
    async def handler(request):
        async with request.app[database].begin() as conn:
            await conn.execute("DELETE * FROM table")
    

Although it` is a [`dict`](https://docs.python.org/3/library/stdtypes.html#dict "\(in Python v3.14\)")-like object, it can’t be duplicated like one using `copy()`.

The class inherits [`dict`](https://docs.python.org/3/library/stdtypes.html#dict "\(in Python v3.14\)").

Parameters:
    

  * **logger** – 

[`logging.Logger`](https://docs.python.org/3/library/logging.html#logging.Logger "\(in Python v3.14\)") instance for storing application logs.

By default the value is `logging.getLogger("aiohttp.web")`

  * **router** – 

[`aiohttp.abc.AbstractRouter`](abc.html#aiohttp.abc.AbstractRouter "aiohttp.abc.AbstractRouter") instance, the system
    

creates `UrlDispatcher` by default if _router_ is `None`.

Deprecated since version 3.3: The custom routers support is deprecated, the parameter will be removed in 4.0.

  * **middlewares** – [`list`](https://docs.python.org/3/library/stdtypes.html#list "\(in Python v3.14\)") of middleware factories, see [Middlewares](web_advanced.html#aiohttp-web-middlewares) for details.

  * **handler_args** – dict-like object that overrides keyword arguments of `Application.make_handler()`

  * **client_max_size** – client’s maximum size in a request, in bytes. If a POST request exceeds this value, it raises an HTTPRequestEntityTooLarge exception.

  * **loop** – 

event loop

Deprecated since version 2.0: The parameter is deprecated. Loop is get set during freeze stage.

  * **debug** – 

Switches debug mode.

Deprecated since version 3.5: Use asyncio [Debug Mode](https://docs.python.org/3/library/asyncio-dev.html#asyncio-debug-mode "\(in Python v3.14\)") instead.




router¶
    

Read-only property that returns _router instance_.

logger¶
    

[`logging.Logger`](https://docs.python.org/3/library/logging.html#logging.Logger "\(in Python v3.14\)") instance for storing application logs.

loop¶
    

[event loop](https://docs.python.org/3/library/asyncio-eventloop.html#asyncio-event-loop "\(in Python v3.14\)") used for processing HTTP requests.

Deprecated since version 3.5.

debug¶
    

Boolean value indicating whether the debug mode is turned on or off.

Deprecated since version 3.5: Use asyncio [Debug Mode](https://docs.python.org/3/library/asyncio-dev.html#asyncio-debug-mode "\(in Python v3.14\)") instead.

on_response_prepare¶
    

A [`Signal`](https://aiosignal.aio-libs.org/en/stable/#aiosignal.Signal "\(in aiosignal v1.4\)") that is fired near the end of `StreamResponse.prepare()` with parameters _request_ and _response_. It can be used, for example, to add custom headers to each response, or to modify the default headers computed by the application, directly before sending the headers to the client.

Signal handlers should have the following signature:
    
    
    async def on_prepare(request, response):
        pass
    

Note

The headers are written immediately after these callbacks are run. Therefore, if you modify the content of the response, you may need to adjust the Content-Length header or similar to match. Aiohttp will not make any updates to the headers from this point.

on_startup¶
    

A [`Signal`](https://aiosignal.aio-libs.org/en/stable/#aiosignal.Signal "\(in aiosignal v1.4\)") that is fired on application start-up.

Subscribers may use the signal to run background tasks in the event loop along with the application’s request handler just after the application start-up.

Signal handlers should have the following signature:
    
    
    async def on_startup(app):
        pass
    

See also

[Signals](web_advanced.html#aiohttp-web-signals).

on_shutdown¶
    

A [`Signal`](https://aiosignal.aio-libs.org/en/stable/#aiosignal.Signal "\(in aiosignal v1.4\)") that is fired on application shutdown.

Subscribers may use the signal for gracefully closing long running connections, e.g. websockets and data streaming.

Signal handlers should have the following signature:
    
    
    async def on_shutdown(app):
        pass
    

It’s up to end user to figure out which [web-handler](glossary.html#term-web-handler)s are still alive and how to finish them properly.

We suggest keeping a list of long running handlers in `Application` dictionary.

See also

[Graceful shutdown](web_advanced.html#aiohttp-web-graceful-shutdown) and `on_cleanup`.

on_cleanup¶
    

A [`Signal`](https://aiosignal.aio-libs.org/en/stable/#aiosignal.Signal "\(in aiosignal v1.4\)") that is fired on application cleanup.

Subscribers may use the signal for gracefully closing connections to database server etc.

Signal handlers should have the following signature:
    
    
    async def on_cleanup(app):
        pass
    

See also

[Signals](web_advanced.html#aiohttp-web-signals) and `on_shutdown`.

cleanup_ctx¶
    

A list of _context generators_ for _startup_ /_cleanup_ handling.

Signal handlers should have the following signature:
    
    
    @contextlib.asynccontextmanager
    async def context(app: web.Application) -> AsyncIterator[None]:
        # do startup stuff
        yield
        # do cleanup
    

Added in version 3.1.

See also

[Cleanup Context](web_advanced.html#aiohttp-web-cleanup-ctx).

add_subapp(_prefix_ , _subapp_)[[source]](_modules/aiohttp/web_app.html#Application.add_subapp)¶
    

Register nested sub-application under given path _prefix_.

In resolving process if request’s path starts with _prefix_ then further resolving is passed to _subapp_.

Parameters:
    

  * **prefix** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – path’s prefix for the resource.

  * **subapp** (_Application_) – nested application attached under _prefix_.



Returns:
    

a `PrefixedSubAppResource` instance.

add_domain(_domain_ , _subapp_)[[source]](_modules/aiohttp/web_app.html#Application.add_domain)¶
    

Register nested sub-application that serves the domain name or domain name mask.

In resolving process if request.headers[‘host’] matches the pattern _domain_ then further resolving is passed to _subapp_.

Warning

Registering many domains using this method may cause performance issues with handler routing. If you have a substantial number of applications for different domains, you may want to consider using a reverse proxy (such as Nginx) to handle routing to different apps, rather that registering them as sub-applications.

Parameters:
    

  * **domain** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – domain or mask of domain for the resource.

  * **subapp** (_Application_) – nested application.



Returns:
    

a `MatchedSubAppResource` instance.

add_routes(_routes_table_)[[source]](_modules/aiohttp/web_app.html#Application.add_routes)¶
    

Register route definitions from _routes_table_.

The table is a [`list`](https://docs.python.org/3/library/stdtypes.html#list "\(in Python v3.14\)") of `RouteDef` items or `RouteTableDef`.

Returns:
    

[`list`](https://docs.python.org/3/library/stdtypes.html#list "\(in Python v3.14\)") of registered `AbstractRoute` instances.

The method is a shortcut for `app.router.add_routes(routes_table)`, see also `UrlDispatcher.add_routes()`.

Added in version 3.1.

Changed in version 3.7: Return value updated from `None` to [`list`](https://docs.python.org/3/library/stdtypes.html#list "\(in Python v3.14\)") of `AbstractRoute` instances.

make_handler(_loop =None_, _** kwargs_)[[source]](_modules/aiohttp/web_app.html#Application.make_handler)¶
    

Creates HTTP protocol factory for handling requests.

Parameters:
    

  * **loop** – 

[event loop](https://docs.python.org/3/library/asyncio-eventloop.html#asyncio-event-loop "\(in Python v3.14\)") used for processing HTTP requests.

If param is `None` [`asyncio.get_event_loop()`](https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.get_event_loop "\(in Python v3.14\)") used for getting default event loop.

Deprecated since version 2.0.

  * **tcp_keepalive** ([_bool_](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)")) – Enable TCP Keep-Alive. Default: `True`.

  * **keepalive_timeout** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – Number of seconds before closing Keep-Alive connection. Default: `75` seconds (NGINX’s default value).

  * **logger** – Custom logger object. Default: `aiohttp.log.server_logger`.

  * **access_log** – Custom logging object. Default: `aiohttp.log.access_logger`.

  * **access_log_class** – Class for access_logger. Default: `aiohttp.helpers.AccessLogger`. Must to be a subclass of [`aiohttp.abc.AbstractAccessLogger`](abc.html#aiohttp.abc.AbstractAccessLogger "aiohttp.abc.AbstractAccessLogger").

  * **access_log_format** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – Access log format string. Default: `helpers.AccessLogger.LOG_FORMAT`.

  * **max_line_size** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – Optional maximum header line size. Default: `8190`.

  * **max_headers** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – Optional maximum header size. Default: `32768`.

  * **max_field_size** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – Optional maximum header field size. Default: `8190`.

  * **lingering_time** ([_float_](https://docs.python.org/3/library/functions.html#float "\(in Python v3.14\)")) – Maximum time during which the server reads and ignores additional data coming from the client when lingering close is on. Use `0` to disable lingering on server channel closing.




You should pass result of the method as _protocol_factory_ to `create_server()`, e.g.:
    
    
    loop = asyncio.get_event_loop()
    
    app = Application()
    
    # setup route table
    # app.router.add_route(...)
    
    await loop.create_server(app.make_handler(),
                             '0.0.0.0', 8080)
    

Deprecated since version 3.2: The method is deprecated and will be removed in future aiohttp versions. Please use [Application runners](web_advanced.html#aiohttp-web-app-runners) instead.

async startup()[[source]](_modules/aiohttp/web_app.html#Application.startup)¶
    

A [coroutine](https://docs.python.org/3/library/asyncio-task.html#coroutine "\(in Python v3.14\)") that will be called along with the application’s request handler.

The purpose of the method is calling `on_startup` signal handlers.

async shutdown()[[source]](_modules/aiohttp/web_app.html#Application.shutdown)¶
    

A [coroutine](https://docs.python.org/3/library/asyncio-task.html#coroutine "\(in Python v3.14\)") that should be called on server stopping but before `cleanup()`.

The purpose of the method is calling `on_shutdown` signal handlers.

async cleanup()[[source]](_modules/aiohttp/web_app.html#Application.cleanup)¶
    

A [coroutine](https://docs.python.org/3/library/asyncio-task.html#coroutine "\(in Python v3.14\)") that should be called on server stopping but after `shutdown()`.

The purpose of the method is calling `on_cleanup` signal handlers.

Note

Application object has `router` attribute but has no `add_route()` method. The reason is: we want to support different router implementations (even maybe not url-matching based but traversal ones).

For sake of that fact we have very trivial ABC for [`AbstractRouter`](abc.html#aiohttp.abc.AbstractRouter "aiohttp.abc.AbstractRouter"): it should have only [`aiohttp.abc.AbstractRouter.resolve()`](abc.html#aiohttp.abc.AbstractRouter.resolve "aiohttp.abc.AbstractRouter.resolve") coroutine.

No methods for adding routes or route reversing (getting URL by route name). All those are router implementation details (but, sure, you need to deal with that methods after choosing the router for your application).

class aiohttp.web.AppKey(_name_ , _t_)[[source]](_modules/aiohttp/helpers.html#AppKey)¶
    

This class should be used for the keys in `Application`. They provide a type-safe alternative to str keys when checking your code with a type checker (e.g. mypy). They also avoid name clashes with keys from different libraries etc.

Parameters:
    

  * **name** – A name to help with debugging. This should be the same as the variable name (much like how [`typing.TypeVar`](https://docs.python.org/3/library/typing.html#typing.TypeVar "\(in Python v3.14\)") is used).

  * **t** – The type that should be used for the value in the dict (e.g. str, Iterator[int] etc.)




class aiohttp.web.Server[[source]](_modules/aiohttp/web_server.html#Server)¶
    

A protocol factory compatible with `create_server()`.

The class is responsible for creating HTTP protocol objects that can handle HTTP connections.

connections¶
    

List of all currently opened connections.

requests_count¶
    

Amount of processed requests.

async shutdown(_timeout_)[[source]](_modules/aiohttp/web_server.html#Server.shutdown)¶
    

A [coroutine](https://docs.python.org/3/library/asyncio-task.html#coroutine "\(in Python v3.14\)") that should be called to close all opened connections.

class aiohttp.web.UrlDispatcher[[source]](_modules/aiohttp/web_urldispatcher.html#UrlDispatcher)¶
    

For dispatching URLs to [handlers](web_quickstart.html#aiohttp-web-handler) [`aiohttp.web`](web.html#module-aiohttp.web "aiohttp.web") uses _routers_ , which is any object that implements [`AbstractRouter`](abc.html#aiohttp.abc.AbstractRouter "aiohttp.abc.AbstractRouter") interface.

This class is a straightforward url-matching router, implementing [`collections.abc.Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping "\(in Python v3.14\)") for access to _named routes_.

`Application` uses this class as `router()` by default.

Before running an `Application` you should fill _route table_ first by calling `add_route()` and `add_static()`.

[Handler](web_quickstart.html#aiohttp-web-handler) lookup is performed by iterating on added _routes_ in FIFO order. The first matching _route_ will be used to call the corresponding _handler_.

If during route creation you specify _name_ parameter the result is a _named route_.

A _named route_ can be retrieved by a `app.router[name]` call, checking for existence can be done with `name in app.router` etc.

See also

Route classes

add_resource(_path_ , _*_ , _name =None_)[[source]](_modules/aiohttp/web_urldispatcher.html#UrlDispatcher.add_resource)¶
    

Append a [resource](glossary.html#term-resource) to the end of route table.

_path_ may be either _constant_ string like `'/a/b/c'` or _variable rule_ like `'/a/{var}'` (see [handling variable paths](web_quickstart.html#aiohttp-web-variable-handler))

Parameters:
    

  * **path** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – resource path spec.

  * **name** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – optional resource name.



Returns:
    

created resource instance (`PlainResource` or `DynamicResource`).

add_route(_method_ , _path_ , _handler_ , _*_ , _name =None_, _expect_handler =None_)[[source]](_modules/aiohttp/web_urldispatcher.html#UrlDispatcher.add_route)¶
    

Append [handler](web_quickstart.html#aiohttp-web-handler) to the end of route table.

_path_ may be either _constant_ string like `'/a/b/c'` or
    

 _variable rule_ like `'/a/{var}'` (see [handling variable paths](web_quickstart.html#aiohttp-web-variable-handler))

Pay attention please: _handler_ is converted to coroutine internally when it is a regular function.

Parameters:
    

  * **method** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – 

HTTP method for route. Should be one of `'GET'`, `'POST'`, `'PUT'`, `'DELETE'`, `'PATCH'`, `'HEAD'`, `'OPTIONS'` or `'*'` for any method.

The parameter is case-insensitive, e.g. you can push `'get'` as well as `'GET'`.

  * **path** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – route path. Should be started with slash (`'/'`).

  * **handler** ([_collections.abc.Callable_](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable "\(in Python v3.14\)")) – route handler.

  * **name** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – optional route name.

  * **expect_handler** ([_collections.abc.Coroutine_](https://docs.python.org/3/library/collections.abc.html#collections.abc.Coroutine "\(in Python v3.14\)")) – optional _expect_ header handler.



Returns:
    

new `AbstractRoute` instance.

add_routes(_routes_table_)[[source]](_modules/aiohttp/web_urldispatcher.html#UrlDispatcher.add_routes)¶
    

Register route definitions from _routes_table_.

The table is a [`list`](https://docs.python.org/3/library/stdtypes.html#list "\(in Python v3.14\)") of `RouteDef` items or `RouteTableDef`.

Returns:
    

[`list`](https://docs.python.org/3/library/stdtypes.html#list "\(in Python v3.14\)") of registered `AbstractRoute` instances.

Added in version 2.3.

Changed in version 3.7: Return value updated from `None` to [`list`](https://docs.python.org/3/library/stdtypes.html#list "\(in Python v3.14\)") of `AbstractRoute` instances.

add_get(_path_ , _handler_ , _*_ , _name =None_, _allow_head =True_, _** kwargs_)[[source]](_modules/aiohttp/web_urldispatcher.html#UrlDispatcher.add_get)¶
    

Shortcut for adding a GET handler. Calls the `add_route()` with `method` equals to `'GET'`.

If _allow_head_ is `True` (default) the route for method HEAD is added with the same handler as for GET.

If _name_ is provided the name for HEAD route is suffixed with `'-head'`. For example `router.add_get(path, handler, name='route')` call adds two routes: first for GET with name `'route'` and second for HEAD with name `'route-head'`.

add_post(_path_ , _handler_ , _** kwargs_)[[source]](_modules/aiohttp/web_urldispatcher.html#UrlDispatcher.add_post)¶
    

Shortcut for adding a POST handler. Calls the `add_route()` with 

`method` equals to `'POST'`.

add_head(_path_ , _handler_ , _** kwargs_)[[source]](_modules/aiohttp/web_urldispatcher.html#UrlDispatcher.add_head)¶
    

Shortcut for adding a HEAD handler. Calls the `add_route()` with `method` equals to `'HEAD'`.

add_put(_path_ , _handler_ , _** kwargs_)[[source]](_modules/aiohttp/web_urldispatcher.html#UrlDispatcher.add_put)¶
    

Shortcut for adding a PUT handler. Calls the `add_route()` with `method` equals to `'PUT'`.

add_patch(_path_ , _handler_ , _** kwargs_)[[source]](_modules/aiohttp/web_urldispatcher.html#UrlDispatcher.add_patch)¶
    

Shortcut for adding a PATCH handler. Calls the `add_route()` with `method` equals to `'PATCH'`.

add_delete(_path_ , _handler_ , _** kwargs_)[[source]](_modules/aiohttp/web_urldispatcher.html#UrlDispatcher.add_delete)¶
    

Shortcut for adding a DELETE handler. Calls the `add_route()` with `method` equals to `'DELETE'`.

add_view(_path_ , _handler_ , _** kwargs_)[[source]](_modules/aiohttp/web_urldispatcher.html#UrlDispatcher.add_view)¶
    

Shortcut for adding a class-based view handler. Calls the `add_route()` with `method` equals to `'*'`.

Added in version 3.0.

add_static(_prefix_ , _path_ , _*_ , _name =None_, _expect_handler =None_, _chunk_size =256 * 1024_, _response_factory =StreamResponse_, _show_index =False_, _follow_symlinks =False_, _append_version =False_)[[source]](_modules/aiohttp/web_urldispatcher.html#UrlDispatcher.add_static)¶
    

Adds a router and a handler for returning static files.

Useful for serving static content like images, javascript and css files.

On platforms that support it, the handler will transfer files more efficiently using the `sendfile` system call.

In some situations it might be necessary to avoid using the `sendfile` system call even if the platform supports it. This can be accomplished by by setting environment variable `AIOHTTP_NOSENDFILE=1`.

If a Brotli or gzip compressed version of the static content exists at the requested path with the `.br` or `.gz` extension, it will be used for the response. Brotli will be preferred over gzip if both files exist.

Warning

Use `add_static()` for development only. In production, static content should be processed by web servers like _nginx_ or _apache_. Such web servers will be able to provide significantly better performance and security for static assets. Several past security vulnerabilities in aiohttp only affected applications using `add_static()`.

Parameters:
    

  * **prefix** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – URL path prefix for handled static files

  * **path** – path to the folder in file system that contains handled static files, [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") or [`pathlib.Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path "\(in Python v3.14\)").

  * **name** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – optional route name.

  * **expect_handler** ([_collections.abc.Coroutine_](https://docs.python.org/3/library/collections.abc.html#collections.abc.Coroutine "\(in Python v3.14\)")) – optional _expect_ header handler.

  * **chunk_size** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – 

size of single chunk for file downloading, 256Kb by default.

Increasing _chunk_size_ parameter to, say, 1Mb may increase file downloading speed but consumes more memory.

  * **show_index** ([_bool_](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)")) – flag for allowing to show indexes of a directory, by default it’s not allowed and HTTP/403 will be returned on directory access.

  * **follow_symlinks** ([_bool_](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)")) – flag for allowing to follow symlinks that lead outside the static root directory, by default it’s not allowed and HTTP/404 will be returned on access. Enabling `follow_symlinks` can be a security risk, and may lead to a directory transversal attack. You do NOT need this option to follow symlinks which point to somewhere else within the static directory, this option is only used to break out of the security sandbox. Enabling this option is highly discouraged, and only expected to be used for edge cases in a local development setting where remote users do not have access to the server.

  * **append_version** ([_bool_](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)")) – flag for adding file version (hash) to the url query string, this value will be used as default when you call to `url()` and `url_for()` methods.



Returns:
    

new `AbstractRoute` instance.

async resolve(_request_)[[source]](_modules/aiohttp/web_urldispatcher.html#UrlDispatcher.resolve)¶
    

A [coroutine](https://docs.python.org/3/library/asyncio-task.html#coroutine "\(in Python v3.14\)") that returns [`AbstractMatchInfo`](abc.html#aiohttp.abc.AbstractMatchInfo "aiohttp.abc.AbstractMatchInfo") for _request_.

The method never raises exception, but returns [`AbstractMatchInfo`](abc.html#aiohttp.abc.AbstractMatchInfo "aiohttp.abc.AbstractMatchInfo") instance with:

  1. [`http_exception`](abc.html#aiohttp.abc.AbstractMatchInfo.http_exception "aiohttp.abc.AbstractMatchInfo.http_exception") assigned to `HTTPException` instance.

  2. [`handler()`](abc.html#aiohttp.abc.AbstractMatchInfo.handler "aiohttp.abc.AbstractMatchInfo.handler") which raises `HTTPNotFound` or `HTTPMethodNotAllowed` on handler’s execution if there is no registered route for _request_.

_Middlewares_ can process that exceptions to render pretty-looking error page for example.




Used by internal machinery, end user unlikely need to call the method.

Note

The method uses `aiohttp.web.BaseRequest.raw_path` for pattern matching against registered routes.

resources()[[source]](_modules/aiohttp/web_urldispatcher.html#UrlDispatcher.resources)¶
    

The method returns a _view_ for _all_ registered resources.

The view is an object that allows to:

  1. Get size of the router table:
         
         len(app.router.resources())
         

  2. Iterate over registered resources:
         
         for resource in app.router.resources():
             print(resource)
         

  3. Make a check if the resources is registered in the router table:
         
         route in app.router.resources()
         




routes()[[source]](_modules/aiohttp/web_urldispatcher.html#UrlDispatcher.routes)¶
    

The method returns a _view_ for _all_ registered routes.

named_resources()[[source]](_modules/aiohttp/web_urldispatcher.html#UrlDispatcher.named_resources)¶
    

Returns a [`dict`](https://docs.python.org/3/library/stdtypes.html#dict "\(in Python v3.14\)")-like [`types.MappingProxyType`](https://docs.python.org/3/library/types.html#types.MappingProxyType "\(in Python v3.14\)") _view_ over _all_ named **resources**.

The view maps every named resource’s **name** to the `AbstractResource` instance. It supports the usual [`dict`](https://docs.python.org/3/library/stdtypes.html#dict "\(in Python v3.14\)")-like operations, except for any mutable operations (i.e. it’s **read-only**):
    
    
    len(app.router.named_resources())
    
    for name, resource in app.router.named_resources().items():
        print(name, resource)
    
    "name" in app.router.named_resources()
    
    app.router.named_resources()["name"]
    

### Resource¶

Default router `UrlDispatcher` operates with [resource](glossary.html#term-resource)s.

Resource is an item in _routing table_ which has a _path_ , an optional unique _name_ and at least one [route](glossary.html#term-route).

[web-handler](glossary.html#term-web-handler) lookup is performed in the following way:

  1. The router splits the URL and checks the index from longest to shortest. For example, ‘/one/two/three’ will first check the index for ‘/one/two/three’, then ‘/one/two’ and finally ‘/’.

  2. If the URL part is found in the index, the list of routes for that URL part is iterated over. If a route matches to requested HTTP method (or `'*'` wildcard) the route’s handler is used as the chosen [web-handler](glossary.html#term-web-handler). The lookup is finished.

  3. If the route is not found in the index, the router tries to find the route in the list of `MatchedSubAppResource`, (current only created from `add_domain()`), and will iterate over the list of `MatchedSubAppResource` in a linear fashion until a match is found.

  4. If no _resource_ / _route_ pair was found, the _router_ returns the special [`AbstractMatchInfo`](abc.html#aiohttp.abc.AbstractMatchInfo "aiohttp.abc.AbstractMatchInfo") instance with [`aiohttp.abc.AbstractMatchInfo.http_exception`](abc.html#aiohttp.abc.AbstractMatchInfo.http_exception "aiohttp.abc.AbstractMatchInfo.http_exception") is not `None` but `HTTPException` with either _HTTP 404 Not Found_ or _HTTP 405 Method Not Allowed_ status code. Registered [`handler()`](abc.html#aiohttp.abc.AbstractMatchInfo.handler "aiohttp.abc.AbstractMatchInfo.handler") raises this exception on call.




Fixed paths are preferred over variable paths. For example, if you have two routes `/a/b` and `/a/{name}`, then the first route will always be preferred over the second one.

If there are multiple dynamic paths with the same fixed prefix, they will be resolved in order of registration.

For example, if you have two dynamic routes that are prefixed with the fixed `/users` path such as `/users/{x}/{y}/z` and `/users/{x}/y/z`, the first one will be preferred over the second one.

User should never instantiate resource classes but give it by `UrlDispatcher.add_resource()` call.

After that he may add a [route](glossary.html#term-route) by calling `Resource.add_route()`.

`UrlDispatcher.add_route()` is just shortcut for:
    
    
    router.add_resource(path).add_route(method, handler)
    

Resource with a _name_ is called _named resource_. The main purpose of _named resource_ is constructing URL by route name for passing it into _template engine_ for example:
    
    
    url = app.router['resource_name'].url_for().with_query({'a': 1, 'b': 2})
    

Resource classes hierarchy:
    
    
    AbstractResource
      Resource
        PlainResource
        DynamicResource
      PrefixResource
        StaticResource
        PrefixedSubAppResource
           MatchedSubAppResource
    

class aiohttp.web.AbstractResource[[source]](_modules/aiohttp/web_urldispatcher.html#AbstractResource)¶
    

A base class for all resources.

Inherited from [`collections.abc.Sized`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Sized "\(in Python v3.14\)") and [`collections.abc.Iterable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterable "\(in Python v3.14\)").

`len(resource)` returns amount of [route](glossary.html#term-route)s belongs to the resource, `for route in resource` allows to iterate over these routes.

name¶
    

Read-only _name_ of resource or `None`.

canonical¶
    

Read-only _canonical path_ associate with the resource. For example `/path/to` or `/path/{to}`

Added in version 3.3.

async resolve(_request_)[[source]](_modules/aiohttp/web_urldispatcher.html#AbstractResource.resolve)¶
    

Resolve resource by finding appropriate [web-handler](glossary.html#term-web-handler) for `(method, path)` combination.

Returns:
    

(_match_info_ , _allowed_methods_) pair.

_allowed_methods_ is a [`set`](https://docs.python.org/3/library/stdtypes.html#set "\(in Python v3.14\)") or HTTP methods accepted by resource.

_match_info_ is either `UrlMappingMatchInfo` if request is resolved or `None` if no [route](glossary.html#term-route) is found.

get_info()[[source]](_modules/aiohttp/web_urldispatcher.html#AbstractResource.get_info)¶
    

A resource description, e.g. `{'path': '/path/to'}` or `{'formatter': '/path/{to}', 'pattern': re.compile(r'^/path/(?P<to>[a-zA-Z][_a-zA-Z0-9]+)$`

url_for(_* args_, _** kwargs_)[[source]](_modules/aiohttp/web_urldispatcher.html#AbstractResource.url_for)¶
    

Construct an URL for route with additional params.

_args_ and **kwargs** depend on a parameters list accepted by inherited resource class.

Returns:
    

[`URL`](https://yarl.aio-libs.org/en/stable/api/#yarl.URL "\(in yarl v1.24\)") – resulting URL instance.

class aiohttp.web.Resource[[source]](_modules/aiohttp/web_urldispatcher.html#Resource)¶
    

A base class for new-style resources, inherits `AbstractResource`.

add_route(_method_ , _handler_ , _*_ , _expect_handler =None_)[[source]](_modules/aiohttp/web_urldispatcher.html#Resource.add_route)¶
    

Add a [web-handler](glossary.html#term-web-handler) to resource.

Parameters:
    

  * **method** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – 

HTTP method for route. Should be one of `'GET'`, `'POST'`, `'PUT'`, `'DELETE'`, `'PATCH'`, `'HEAD'`, `'OPTIONS'` or `'*'` for any method.

The parameter is case-insensitive, e.g. you can push `'get'` as well as `'GET'`.

The method should be unique for resource.

  * **handler** ([_collections.abc.Callable_](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable "\(in Python v3.14\)")) – route handler.

  * **expect_handler** ([_collections.abc.Coroutine_](https://docs.python.org/3/library/collections.abc.html#collections.abc.Coroutine "\(in Python v3.14\)")) – optional _expect_ header handler.



Returns:
    

new `ResourceRoute` instance.

class aiohttp.web.PlainResource[[source]](_modules/aiohttp/web_urldispatcher.html#PlainResource)¶
    

A resource, inherited from `Resource`.

The class corresponds to resources with plain-text matching, `'/path/to'` for example.

canonical¶
    

Read-only _canonical path_ associate with the resource. Returns the path used to create the PlainResource. For example `/path/to`

Added in version 3.3.

url_for()[[source]](_modules/aiohttp/web_urldispatcher.html#PlainResource.url_for)¶
    

Returns a [`URL`](https://yarl.aio-libs.org/en/stable/api/#yarl.URL "\(in yarl v1.24\)") for the resource.

class aiohttp.web.DynamicResource[[source]](_modules/aiohttp/web_urldispatcher.html#DynamicResource)¶
    

A resource, inherited from `Resource`.

The class corresponds to resources with [variable](web_quickstart.html#aiohttp-web-variable-handler) matching, e.g. `'/path/{to}/{param}'` etc.

canonical¶
    

Read-only _canonical path_ associate with the resource. Returns the formatter obtained from the path used to create the DynamicResource. For example, from a path `/get/{num:^\d+}`, it returns `/get/{num}`

Added in version 3.3.

url_for(_** params_)[[source]](_modules/aiohttp/web_urldispatcher.html#DynamicResource.url_for)¶
    

Returns a [`URL`](https://yarl.aio-libs.org/en/stable/api/#yarl.URL "\(in yarl v1.24\)") for the resource.

Parameters:
    

**params** – 

– a variable substitutions for dynamic resource.

E.g. for `'/path/{to}/{param}'` pattern the method should be called as `resource.url_for(to='val1', param='val2')`

class aiohttp.web.StaticResource[[source]](_modules/aiohttp/web_urldispatcher.html#StaticResource)¶
    

A resource, inherited from `Resource`.

The class corresponds to resources for [static file serving](web_advanced.html#aiohttp-web-static-file-handling).

canonical¶
    

Read-only _canonical path_ associate with the resource. Returns the prefix used to create the StaticResource. For example `/prefix`

Added in version 3.3.

url_for(_filename_ , _append_version =None_)[[source]](_modules/aiohttp/web_urldispatcher.html#StaticResource.url_for)¶
    

Returns a [`URL`](https://yarl.aio-libs.org/en/stable/api/#yarl.URL "\(in yarl v1.24\)") for file path under resource prefix.

Parameters:
    

  * **filename** – 

– a file name substitution for static file handler.

Accepts both [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") and [`pathlib.Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path "\(in Python v3.14\)").

E.g. an URL for `'/prefix/dir/file.txt'` should be generated as `resource.url_for(filename='dir/file.txt')`

  * **append_version** ([_bool_](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)")) – 

– a flag for adding file version
    

(hash) to the url query string for cache boosting

By default has value from a constructor (`False` by default) When set to `True` \- `v=FILE_HASH` query string param will be added When set to `False` has no impact

if file not found has no impact




class aiohttp.web.PrefixedSubAppResource[[source]](_modules/aiohttp/web_urldispatcher.html#PrefixedSubAppResource)¶
    

A resource for serving nested applications. The class instance is returned by `add_subapp` call.

canonical¶
    

Read-only _canonical path_ associate with the resource. Returns the prefix used to create the PrefixedSubAppResource. For example `/prefix`

Added in version 3.3.

url_for(_** kwargs_)[[source]](_modules/aiohttp/web_urldispatcher.html#PrefixedSubAppResource.url_for)¶
    

The call is not allowed, it raises [`RuntimeError`](https://docs.python.org/3/library/exceptions.html#RuntimeError "\(in Python v3.14\)").

### Route¶

Route has _HTTP method_ (wildcard `'*'` is an option), [web-handler](glossary.html#term-web-handler) and optional _expect handler_.

Every route belong to some resource.

Route classes hierarchy:
    
    
    AbstractRoute
      ResourceRoute
      SystemRoute
    

`ResourceRoute` is the route used for resources, `SystemRoute` serves URL resolving errors like _404 Not Found_ and _405 Method Not Allowed_.

class aiohttp.web.AbstractRoute[[source]](_modules/aiohttp/web_urldispatcher.html#AbstractRoute)¶
    

Base class for routes served by `UrlDispatcher`.

method¶
    

HTTP method handled by the route, e.g. _GET_ , _POST_ etc.

handler¶
    

[handler](web_quickstart.html#aiohttp-web-handler) that processes the route.

name¶
    

Name of the route, always equals to name of resource which owns the route.

resource¶
    

Resource instance which holds the route, `None` for `SystemRoute`.

url_for(_* args_, _** kwargs_)[[source]](_modules/aiohttp/web_urldispatcher.html#AbstractRoute.url_for)¶
    

Abstract method for constructing url handled by the route.

Actually it’s a shortcut for `route.resource.url_for(...)`.

async handle_expect_header(_request_)[[source]](_modules/aiohttp/web_urldispatcher.html#AbstractRoute.handle_expect_header)¶
    

`100-continue` handler.

class aiohttp.web.ResourceRoute[[source]](_modules/aiohttp/web_urldispatcher.html#ResourceRoute)¶
    

The route class for handling different HTTP methods for `Resource`.

class aiohttp.web.SystemRoute¶
    

The route class for handling URL resolution errors like like _404 Not Found_ and _405 Method Not Allowed_.

status¶
    

HTTP status code

reason¶
    

HTTP status reason

### RouteDef and StaticDef¶

Route definition, a description for not registered yet route.

Could be used for filing route table by providing a list of route definitions (Django style).

The definition is created by functions like `get()` or `post()`, list of definitions could be added to router by `UrlDispatcher.add_routes()` call:
    
    
    from aiohttp import web
    
    async def handle_get(request):
        ...
    
    
    async def handle_post(request):
        ...
    
    app.router.add_routes([web.get('/get', handle_get),
                           web.post('/post', handle_post),
    

class aiohttp.web.AbstractRouteDef[[source]](_modules/aiohttp/web_routedef.html#AbstractRouteDef)¶
    

A base class for route definitions.

Inherited from [`abc.ABC`](https://docs.python.org/3/library/abc.html#abc.ABC "\(in Python v3.14\)").

Added in version 3.1.

register(_router_)[[source]](_modules/aiohttp/web_routedef.html#AbstractRouteDef.register)¶
    

Register itself into `UrlDispatcher`.

Abstract method, should be overridden by subclasses.

Returns:
    

[`list`](https://docs.python.org/3/library/stdtypes.html#list "\(in Python v3.14\)") of registered `AbstractRoute` objects.

Changed in version 3.7: Return value updated from `None` to [`list`](https://docs.python.org/3/library/stdtypes.html#list "\(in Python v3.14\)") of `AbstractRoute` instances.

class aiohttp.web.RouteDef[[source]](_modules/aiohttp/web_routedef.html#RouteDef)¶
    

A definition of not registered yet route.

Implements `AbstractRouteDef`.

Added in version 2.3.

Changed in version 3.1: The class implements `AbstractRouteDef` interface.

method¶
    

HTTP method (`GET`, `POST` etc.) ([`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")).

path¶
    

Path to resource, e.g. `/path/to`. Could contain `{}` brackets for [variable resources](web_quickstart.html#aiohttp-web-variable-handler) ([`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")).

handler¶
    

An async function to handle HTTP request.

kwargs¶
    

A [`dict`](https://docs.python.org/3/library/stdtypes.html#dict "\(in Python v3.14\)") of additional arguments.

class aiohttp.web.StaticDef[[source]](_modules/aiohttp/web_routedef.html#StaticDef)¶
    

A definition of static file resource.

Implements `AbstractRouteDef`.

Added in version 3.1.

prefix¶
    

A prefix used for static file handling, e.g. `/static`.

path¶
    

File system directory to serve, [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") or [`pathlib.Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path "\(in Python v3.14\)") (e.g. `'/home/web-service/path/to/static'`.

kwargs¶
    

A [`dict`](https://docs.python.org/3/library/stdtypes.html#dict "\(in Python v3.14\)") of additional arguments, see `UrlDispatcher.add_static()` for a list of supported options.

aiohttp.web.get(_path_ , _handler_ , _*_ , _name =None_, _allow_head =True_, _expect_handler =None_)[[source]](_modules/aiohttp/web_routedef.html#get)¶
    

Return `RouteDef` for processing `GET` requests. See `UrlDispatcher.add_get()` for information about parameters.

Added in version 2.3.

aiohttp.web.post(_path_ , _handler_ , _*_ , _name =None_, _expect_handler =None_)[[source]](_modules/aiohttp/web_routedef.html#post)¶
    

Return `RouteDef` for processing `POST` requests. See `UrlDispatcher.add_post()` for information about parameters.

Added in version 2.3.

aiohttp.web.head(_path_ , _handler_ , _*_ , _name =None_, _expect_handler =None_)[[source]](_modules/aiohttp/web_routedef.html#head)¶
    

Return `RouteDef` for processing `HEAD` requests. See `UrlDispatcher.add_head()` for information about parameters.

Added in version 2.3.

aiohttp.web.put(_path_ , _handler_ , _*_ , _name =None_, _expect_handler =None_)[[source]](_modules/aiohttp/web_routedef.html#put)¶
    

Return `RouteDef` for processing `PUT` requests. See `UrlDispatcher.add_put()` for information about parameters.

Added in version 2.3.

aiohttp.web.patch(_path_ , _handler_ , _*_ , _name =None_, _expect_handler =None_)[[source]](_modules/aiohttp/web_routedef.html#patch)¶
    

Return `RouteDef` for processing `PATCH` requests. See `UrlDispatcher.add_patch()` for information about parameters.

Added in version 2.3.

aiohttp.web.delete(_path_ , _handler_ , _*_ , _name =None_, _expect_handler =None_)[[source]](_modules/aiohttp/web_routedef.html#delete)¶
    

Return `RouteDef` for processing `DELETE` requests. See `UrlDispatcher.add_delete()` for information about parameters.

Added in version 2.3.

aiohttp.web.view(_path_ , _handler_ , _*_ , _name =None_, _expect_handler =None_)[[source]](_modules/aiohttp/web_routedef.html#view)¶
    

Return `RouteDef` for processing `ANY` requests. See `UrlDispatcher.add_view()` for information about parameters.

Added in version 3.0.

aiohttp.web.static(_prefix_ , _path_ , _*_ , _name =None_, _expect_handler =None_, _chunk_size =256 * 1024_, _show_index =False_, _follow_symlinks =False_, _append_version =False_)[[source]](_modules/aiohttp/web_routedef.html#static)¶
    

Return `StaticDef` for processing static files.

See `UrlDispatcher.add_static()` for information about supported parameters.

Added in version 3.1.

aiohttp.web.route(_method_ , _path_ , _handler_ , _*_ , _name =None_, _expect_handler =None_)[[source]](_modules/aiohttp/web_routedef.html#route)¶
    

Return `RouteDef` for processing requests that decided by `method`. See `UrlDispatcher.add_route()` for information about parameters.

Added in version 2.3.

### RouteTableDef¶

A routes table definition used for describing routes by decorators (Flask style):
    
    
    from aiohttp import web
    
    routes = web.RouteTableDef()
    
    @routes.get('/get')
    async def handle_get(request):
        ...
    
    
    @routes.post('/post')
    async def handle_post(request):
        ...
    
    app.router.add_routes(routes)
    
    
    @routes.view("/view")
    class MyView(web.View):
        async def get(self):
            ...
    
        async def post(self):
            ...
    

class aiohttp.web.RouteTableDef[[source]](_modules/aiohttp/web_routedef.html#RouteTableDef)¶
    

A sequence of `RouteDef` instances (implements [`collections.abc.Sequence`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Sequence "\(in Python v3.14\)") protocol).

In addition to all standard [`list`](https://docs.python.org/3/library/stdtypes.html#list "\(in Python v3.14\)") methods the class provides also methods like `get()` and `post()` for adding new route definition.

Added in version 2.3.

@get(_path_ , _*_ , _allow_head =True_, _name =None_, _expect_handler =None_)[[source]](_modules/aiohttp/web_routedef.html#RouteTableDef.get)¶
    

Add a new `RouteDef` item for registering `GET` web-handler.

See `UrlDispatcher.add_get()` for information about parameters.

@post(_path_ , _*_ , _name =None_, _expect_handler =None_)[[source]](_modules/aiohttp/web_routedef.html#RouteTableDef.post)¶
    

Add a new `RouteDef` item for registering `POST` web-handler.

See `UrlDispatcher.add_post()` for information about parameters.

@head(_path_ , _*_ , _name =None_, _expect_handler =None_)[[source]](_modules/aiohttp/web_routedef.html#RouteTableDef.head)¶
    

Add a new `RouteDef` item for registering `HEAD` web-handler.

See `UrlDispatcher.add_head()` for information about parameters.

@put(_path_ , _*_ , _name =None_, _expect_handler =None_)[[source]](_modules/aiohttp/web_routedef.html#RouteTableDef.put)¶
    

Add a new `RouteDef` item for registering `PUT` web-handler.

See `UrlDispatcher.add_put()` for information about parameters.

@patch(_path_ , _*_ , _name =None_, _expect_handler =None_)[[source]](_modules/aiohttp/web_routedef.html#RouteTableDef.patch)¶
    

Add a new `RouteDef` item for registering `PATCH` web-handler.

See `UrlDispatcher.add_patch()` for information about parameters.

@delete(_path_ , _*_ , _name =None_, _expect_handler =None_)[[source]](_modules/aiohttp/web_routedef.html#RouteTableDef.delete)¶
    

Add a new `RouteDef` item for registering `DELETE` web-handler.

See `UrlDispatcher.add_delete()` for information about parameters.

@view(_path_ , _*_ , _name =None_, _expect_handler =None_)[[source]](_modules/aiohttp/web_routedef.html#RouteTableDef.view)¶
    

Add a new `RouteDef` item for registering `ANY` methods against a class-based view.

See `UrlDispatcher.add_view()` for information about parameters.

Added in version 3.0.

static(_prefix_ , _path_ , _*_ , _name =None_, _expect_handler =None_, _chunk_size =256 * 1024_, _show_index =False_, _follow_symlinks =False_, _append_version =False_)[[source]](_modules/aiohttp/web_routedef.html#RouteTableDef.static)¶
    

Add a new `StaticDef` item for registering static files processor.

See `UrlDispatcher.add_static()` for information about supported parameters.

Added in version 3.1.

@route(_method_ , _path_ , _*_ , _name =None_, _expect_handler =None_)[[source]](_modules/aiohttp/web_routedef.html#RouteTableDef.route)¶
    

Add a new `RouteDef` item for registering a web-handler for arbitrary HTTP method.

See `UrlDispatcher.add_route()` for information about parameters.

### MatchInfo¶

After route matching web application calls found handler if any.

Matching result can be accessible from handler as `Request.match_info` attribute.

In general the result may be any object derived from [`AbstractMatchInfo`](abc.html#aiohttp.abc.AbstractMatchInfo "aiohttp.abc.AbstractMatchInfo") (`UrlMappingMatchInfo` for default `UrlDispatcher` router).

class aiohttp.web.UrlMappingMatchInfo[[source]](_modules/aiohttp/web_urldispatcher.html#UrlMappingMatchInfo)¶
    

Inherited from [`dict`](https://docs.python.org/3/library/stdtypes.html#dict "\(in Python v3.14\)") and [`AbstractMatchInfo`](abc.html#aiohttp.abc.AbstractMatchInfo "aiohttp.abc.AbstractMatchInfo"). Dict items are filled by matching info and is [resource](glossary.html#term-resource)-specific.

expect_handler¶
    

A coroutine for handling `100-continue`.

handler¶
    

A coroutine for handling request.

route¶
    

`AbstractRoute` instance for url matching.

### View¶

class aiohttp.web.View(_request_)[[source]](_modules/aiohttp/web_urldispatcher.html#View)¶
    

Inherited from [`AbstractView`](abc.html#aiohttp.abc.AbstractView "aiohttp.abc.AbstractView").

Base class for class based views. Implementations should derive from `View` and override methods for handling HTTP verbs like `get()` or `post()`:
    
    
    class MyView(View):
    
        async def get(self):
            resp = await get_response(self.request)
            return resp
    
        async def post(self):
            resp = await post_response(self.request)
            return resp
    
    app.router.add_view('/view', MyView)
    

The view raises _405 Method Not allowed_ (`HTTPMethodNotAllowed`) if requested web verb is not supported.

Parameters:
    

**request** – instance of `Request` that has initiated a view processing.

request¶
    

Request sent to view’s constructor, read-only property.

Overridable coroutine methods: `connect()`, `delete()`, `get()`, `head()`, `options()`, `patch()`, `post()`, `put()`, `trace()`.

See also

[Class Based Views](web_quickstart.html#aiohttp-web-class-based-views)

## Running Applications¶

To start web application there is `AppRunner` and site classes.

Runner is a storage for running application, sites are for running application on specific TCP or Unix socket, e.g.:
    
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8080)
    await site.start()
    # wait for finish signal
    await runner.cleanup()
    

Added in version 3.0: `AppRunner` / `ServerRunner` and `TCPSite` / `UnixSite` / `SockSite` are added in aiohttp 3.0

class aiohttp.web.BaseRunner[[source]](_modules/aiohttp/web_runner.html#BaseRunner)¶
    

A base class for runners. Use `AppRunner` for serving `Application`, `ServerRunner` for low-level `Server`.

server¶
    

Low-level web `Server` for handling HTTP requests, read-only attribute.

addresses¶
    

A [`list`](https://docs.python.org/3/library/stdtypes.html#list "\(in Python v3.14\)") of served sockets addresses.

See [`socket.getsockname()`](https://docs.python.org/3/library/socket.html#socket.socket.getsockname "\(in Python v3.14\)") for items type.

Added in version 3.3.

sites¶
    

A read-only [`set`](https://docs.python.org/3/library/stdtypes.html#set "\(in Python v3.14\)") of served sites (`TCPSite` / `UnixSite` / `NamedPipeSite` / `SockSite` instances).

async setup()[[source]](_modules/aiohttp/web_runner.html#BaseRunner.setup)¶
    

Initialize the server. Should be called before adding sites.

async cleanup()[[source]](_modules/aiohttp/web_runner.html#BaseRunner.cleanup)¶
    

Stop handling all registered sites and cleanup used resources.

class aiohttp.web.AppRunner(_app_ , _*_ , _handle_signals =False_, _** kwargs_)[[source]](_modules/aiohttp/web_runner.html#AppRunner)¶
    

A runner for `Application`. Used with conjunction with sites to serve on specific port.

Inherited from `BaseRunner`.

Parameters:
    

  * **app** (_Application_) – web application instance to serve.

  * **handle_signals** ([_bool_](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)")) – add signal handlers for [`signal.SIGINT`](https://docs.python.org/3/library/signal.html#signal.SIGINT "\(in Python v3.14\)") and [`signal.SIGTERM`](https://docs.python.org/3/library/signal.html#signal.SIGTERM "\(in Python v3.14\)") (`False` by default). These handlers will raise `GracefulExit`.

  * **kwargs** – named parameters to pass into web protocol.




Supported _kwargs_ :

Parameters:
    

  * **tcp_keepalive** ([_bool_](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)")) – Enable TCP Keep-Alive. Default: `True`.

  * **keepalive_timeout** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – Number of seconds before closing Keep-Alive connection. Default: `3630` seconds (when deployed behind a reverse proxy it’s important for this value to be higher than the proxy’s timeout. To avoid race conditions we always want the proxy to close the connection).

  * **logger** – Custom logger object. Default: `aiohttp.log.server_logger`.

  * **access_log** – Custom logging object. Default: `aiohttp.log.access_logger`.

  * **access_log_class** – Class for access_logger. Default: `aiohttp.helpers.AccessLogger`. Must to be a subclass of [`aiohttp.abc.AbstractAccessLogger`](abc.html#aiohttp.abc.AbstractAccessLogger "aiohttp.abc.AbstractAccessLogger").

  * **access_log_format** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – Access log format string. Default: `helpers.AccessLogger.LOG_FORMAT`.

  * **max_line_size** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – Optional maximum header line size. Default: `8190`.

  * **max_field_size** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – Optional maximum header combined name and value size. Default: `8190`.

  * **max_headers** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – Optional maximum number of headers and trailers combined. Default: `128`.

  * **lingering_time** ([_float_](https://docs.python.org/3/library/functions.html#float "\(in Python v3.14\)")) – Maximum time during which the server reads and ignores additional data coming from the client when lingering close is on. Use `0` to disable lingering on server channel closing.

  * **read_bufsize** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – 

Size of the read buffer (`BaseRequest.content`).
    

`None` by default, it means that the session global value is used.

Added in version 3.7.

  * **auto_decompress** ([_bool_](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)")) – 

Automatically decompress request body, `True` by default.

Added in version 3.8.




app¶
    

Read-only attribute for accessing to `Application` served instance.

async setup()¶
    

Initialize application. Should be called before adding sites.

The method calls `Application.on_startup` registered signals.

async cleanup()¶
    

Stop handling all registered sites and cleanup used resources.

`Application.on_shutdown` and `Application.on_cleanup` signals are called internally.

class aiohttp.web.ServerRunner(_web_server_ , _*_ , _handle_signals =False_, _** kwargs_)[[source]](_modules/aiohttp/web_runner.html#ServerRunner)¶
    

A runner for low-level `Server`. Used with conjunction with sites to serve on specific port.

Inherited from `BaseRunner`.

Parameters:
    

  * **web_server** (_Server_) – low-level web server instance to serve.

  * **handle_signals** ([_bool_](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)")) – add signal handlers for [`signal.SIGINT`](https://docs.python.org/3/library/signal.html#signal.SIGINT "\(in Python v3.14\)") and [`signal.SIGTERM`](https://docs.python.org/3/library/signal.html#signal.SIGTERM "\(in Python v3.14\)") (`False` by default). These handlers will raise `GracefulExit`.

  * **kwargs** – named parameters to pass into web protocol.




See also

[Low Level Server](web_lowlevel.html#aiohttp-web-lowlevel) demonstrates low-level server usage

class aiohttp.web.BaseSite[[source]](_modules/aiohttp/web_runner.html#BaseSite)¶
    

An abstract class for handled sites.

name¶
    

An identifier for site, read-only [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") property. Could be a handled URL or UNIX socket path.

async start()[[source]](_modules/aiohttp/web_runner.html#BaseSite.start)¶
    

Start handling a site.

async stop()[[source]](_modules/aiohttp/web_runner.html#BaseSite.stop)¶
    

Stop handling a site.

class aiohttp.web.TCPSite(_runner_ , _host =None_, _port =None_, _*_ , _shutdown_timeout =60.0_, _ssl_context =None_, _backlog =128_, _reuse_address =None_, _reuse_port =None_)[[source]](_modules/aiohttp/web_runner.html#TCPSite)¶
    

Serve a runner on TCP socket.

Parameters:
    

  * **runner** – a runner to serve.

  * **host** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – HOST to listen on, all interfaces if `None` (default).

  * **port** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – PORT to listen on, `8080` if `None` (default). Use `0` to let the OS assign a free ephemeral port (see `port`).

  * **shutdown_timeout** ([_float_](https://docs.python.org/3/library/functions.html#float "\(in Python v3.14\)")) – a timeout used for both waiting on pending tasks before application shutdown and for closing opened connections on `BaseSite.stop()` call.

  * **ssl_context** – a [`ssl.SSLContext`](https://docs.python.org/3/library/ssl.html#ssl.SSLContext "\(in Python v3.14\)") instance for serving SSL/TLS secure server, `None` for plain HTTP server (default).

  * **backlog** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – 

a number of unaccepted connections that the system will allow before refusing new connections, see [`socket.socket.listen()`](https://docs.python.org/3/library/socket.html#socket.socket.listen "\(in Python v3.14\)") for details.

`128` by default.

  * **reuse_address** ([_bool_](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)")) – tells the kernel to reuse a local socket in TIME_WAIT state, without waiting for its natural timeout to expire. If not specified will automatically be set to True on UNIX.

  * **reuse_port** ([_bool_](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)")) – tells the kernel to allow this endpoint to be bound to the same port as other existing endpoints are bound to, so long as they all set this flag when being created. This option is not supported on Windows.




port¶
    

Read-only. The actual port number the server is bound to, only guaranteed to be correct after the site has been started.

class aiohttp.web.UnixSite(_runner_ , _path_ , _*_ , _shutdown_timeout =60.0_, _ssl_context =None_, _backlog =128_)[[source]](_modules/aiohttp/web_runner.html#UnixSite)¶
    

Serve a runner on UNIX socket.

Parameters:
    

  * **runner** – a runner to serve.

  * **path** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – PATH to UNIX socket to listen.

  * **shutdown_timeout** ([_float_](https://docs.python.org/3/library/functions.html#float "\(in Python v3.14\)")) – a timeout used for both waiting on pending tasks before application shutdown and for closing opened connections on `BaseSite.stop()` call.

  * **ssl_context** – a [`ssl.SSLContext`](https://docs.python.org/3/library/ssl.html#ssl.SSLContext "\(in Python v3.14\)") instance for serving SSL/TLS secure server, `None` for plain HTTP server (default).

  * **backlog** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – 

a number of unaccepted connections that the system will allow before refusing new connections, see [`socket.socket.listen()`](https://docs.python.org/3/library/socket.html#socket.socket.listen "\(in Python v3.14\)") for details.

`128` by default.




class aiohttp.web.NamedPipeSite(_runner_ , _path_ , _*_ , _shutdown_timeout =60.0_)[[source]](_modules/aiohttp/web_runner.html#NamedPipeSite)¶
    

Serve a runner on Named Pipe in Windows.

Parameters:
    

  * **runner** – a runner to serve.

  * **path** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – PATH of named pipe to listen.

  * **shutdown_timeout** ([_float_](https://docs.python.org/3/library/functions.html#float "\(in Python v3.14\)")) – a timeout used for both waiting on pending tasks before application shutdown and for closing opened connections on `BaseSite.stop()` call.




class aiohttp.web.SockSite(_runner_ , _sock_ , _*_ , _shutdown_timeout =60.0_, _ssl_context =None_, _backlog =128_)[[source]](_modules/aiohttp/web_runner.html#SockSite)¶
    

Serve a runner on UNIX socket.

Parameters:
    

  * **runner** – a runner to serve.

  * **sock** – A [socket instance](https://docs.python.org/3/library/socket.html#socket-objects "\(in Python v3.14\)") to listen to.

  * **shutdown_timeout** ([_float_](https://docs.python.org/3/library/functions.html#float "\(in Python v3.14\)")) – a timeout used for both waiting on pending tasks before application shutdown and for closing opened connections on `BaseSite.stop()` call.

  * **ssl_context** – a [`ssl.SSLContext`](https://docs.python.org/3/library/ssl.html#ssl.SSLContext "\(in Python v3.14\)") instance for serving SSL/TLS secure server, `None` for plain HTTP server (default).

  * **backlog** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – 

a number of unaccepted connections that the system will allow before refusing new connections, see [`socket.socket.listen()`](https://docs.python.org/3/library/socket.html#socket.socket.listen "\(in Python v3.14\)") for details.

`128` by default.




exception aiohttp.web.GracefulExit[[source]](_modules/aiohttp/web_runner.html#GracefulExit)¶
    

Raised by signal handlers for [`signal.SIGINT`](https://docs.python.org/3/library/signal.html#signal.SIGINT "\(in Python v3.14\)") and [`signal.SIGTERM`](https://docs.python.org/3/library/signal.html#signal.SIGTERM "\(in Python v3.14\)") defined in `AppRunner` and `ServerRunner` when `handle_signals` is set to `True`.

Inherited from [`SystemExit`](https://docs.python.org/3/library/exceptions.html#SystemExit "\(in Python v3.14\)"), which exits with error code `1` if not handled.

## Utilities¶

class aiohttp.web.FileField[[source]](_modules/aiohttp/web_request.html#FileField)¶
    

A [`dataclass`](https://docs.python.org/3/library/dataclasses.html#module-dataclasses "\(in Python v3.14\)") instance that is returned as multidict value by `aiohttp.web.BaseRequest.post()` if field is uploaded file.

name¶
    

Field name

filename¶
    

File name as specified by uploading (client) side.

file¶
    

An [`io.IOBase`](https://docs.python.org/3/library/io.html#io.IOBase "\(in Python v3.14\)") instance with content of uploaded file.

content_type¶
    

_MIME type_ of uploaded file, `'text/plain'` by default.

See also

[File Uploads](web_quickstart.html#aiohttp-web-file-upload)

aiohttp.web.run_app(_app_ , _*_ , _host =None_, _port =None_, _path =None_, _sock =None_, _shutdown_timeout =60.0_, _keepalive_timeout =3630_, _ssl_context =None_, _print =print_, _backlog =128_, _access_log_class =aiohttp.helpers.AccessLogger_, _access_log_format =aiohttp.helpers.AccessLogger.LOG_FORMAT_, _access_log =aiohttp.log.access_logger_, _handle_signals =True_, _reuse_address =None_, _reuse_port =None_, _handler_cancellation =False_, _** kwargs_)[[source]](_modules/aiohttp/web.html#run_app)¶
    

A high-level function for running an application, serving it until keyboard interrupt and performing a [Graceful shutdown](web_advanced.html#aiohttp-web-graceful-shutdown).

This is a high-level function very similar to [`asyncio.run()`](https://docs.python.org/3/library/asyncio-runner.html#asyncio.run "\(in Python v3.14\)") and should be used as the main entry point for an application. The `Application` object essentially becomes our main() function. If additional tasks need to be run in parallel, see [Complex Applications](web_advanced.html#aiohttp-web-complex-applications).

The server will listen on any host or Unix domain socket path you supply. If no hosts or paths are supplied, or only a port is supplied, a TCP server listening on 0.0.0.0 (all hosts) will be launched.

Distributing HTTP traffic to multiple hosts or paths on the same application process provides no performance benefit as the requests are handled on the same event loop. See [Server Deployment](deployment.html) for ways of distributing work for increased performance.

Parameters:
    

  * **app** – `Application` instance to run or a _coroutine_ that returns an application.

  * **host** ([_str_](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)")) – TCP/IP host or a sequence of hosts for HTTP server. Default is `'0.0.0.0'` if _port_ has been specified or if _path_ is not supplied.

  * **port** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – TCP/IP port for HTTP server. Default is `8080` for plain text HTTP and `8443` for HTTP via SSL (when _ssl_context_ parameter is specified).

  * **path** – file system path for HTTP server Unix domain socket. A sequence of file system paths can be used to bind multiple domain sockets. Listening on Unix domain sockets is not supported by all operating systems, [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)"), [`pathlib.Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path "\(in Python v3.14\)") or an iterable of these.

  * **sock** ([_socket.socket_](https://docs.python.org/3/library/socket.html#socket.socket "\(in Python v3.14\)")) – a preexisting socket object to accept connections on. A sequence of socket objects can be passed.

  * **shutdown_timeout** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – 

a delay to wait for graceful server shutdown before disconnecting all open client sockets hard way.

This is used as a delay to wait for pending tasks to complete and then again to close any pending connections.

A system with properly [Graceful shutdown](web_advanced.html#aiohttp-web-graceful-shutdown) implemented never waits for the second timeout but closes a server in a few milliseconds.

  * **keepalive_timeout** ([_float_](https://docs.python.org/3/library/functions.html#float "\(in Python v3.14\)")) – 

a delay before a TCP connection is
    

closed after a HTTP request. The delay allows for reuse of a TCP connection.

When deployed behind a reverse proxy it’s important for this value to be higher than the proxy’s timeout. To avoid race conditions, we always want the proxy to handle connection closing.

Added in version 3.8.

  * **ssl_context** – [`ssl.SSLContext`](https://docs.python.org/3/library/ssl.html#ssl.SSLContext "\(in Python v3.14\)") for HTTPS server, `None` for HTTP connection.

  * **print** – a callable compatible with [`print()`](https://docs.python.org/3/library/functions.html#print "\(in Python v3.14\)"). May be used to override STDOUT output or suppress it. Passing None disables output.

  * **backlog** ([_int_](https://docs.python.org/3/library/functions.html#int "\(in Python v3.14\)")) – the number of unaccepted connections that the system will allow before refusing new connections (`128` by default).

  * **access_log_class** – class for access_logger. Default: `aiohttp.helpers.AccessLogger`. Must to be a subclass of [`aiohttp.abc.AbstractAccessLogger`](abc.html#aiohttp.abc.AbstractAccessLogger "aiohttp.abc.AbstractAccessLogger").

  * **access_log** – [`logging.Logger`](https://docs.python.org/3/library/logging.html#logging.Logger "\(in Python v3.14\)") instance used for saving access logs. Use `None` for disabling logs for sake of speedup.

  * **access_log_format** – access log format, see [Format specification](logging.html#aiohttp-logging-access-log-format-spec) for details.

  * **handle_signals** ([_bool_](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)")) – override signal TERM handling to gracefully exit the application.

  * **reuse_address** ([_bool_](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)")) – tells the kernel to reuse a local socket in TIME_WAIT state, without waiting for its natural timeout to expire. If not specified will automatically be set to True on UNIX.

  * **reuse_port** ([_bool_](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)")) – tells the kernel to allow this endpoint to be bound to the same port as other existing endpoints are bound to, so long as they all set this flag when being created. This option is not supported on Windows.

  * **handler_cancellation** ([_bool_](https://docs.python.org/3/library/functions.html#bool "\(in Python v3.14\)")) – cancels the web handler task if the client drops the connection. This is recommended if familiar with asyncio behavior or scalability is a concern. [Peer disconnection](web_advanced.html#aiohttp-web-peer-disconnection)

  * **kwargs** – additional named parameters to pass into `AppRunner` constructor.




Added in version 3.0: Support _access_log_class_ parameter.

Support _reuse_address_ , _reuse_port_ parameter.

Added in version 3.1: Accept a coroutine as _app_ parameter.

Added in version 3.9: Support handler_cancellation parameter (this was the default behavior in aiohttp <3.7).

## Constants¶

class aiohttp.web.ContentCoding[[source]](_modules/aiohttp/web_response.html#ContentCoding)¶
    

An [`enum.Enum`](https://docs.python.org/3/library/enum.html#enum.Enum "\(in Python v3.14\)") class of available Content Codings.

deflate¶
    

_DEFLATE compression_

gzip¶
    

_GZIP compression_

identity¶
    

_no compression_

## Middlewares¶

aiohttp.web.normalize_path_middleware(_*_ , _append_slash =True_, _remove_slash =False_, _merge_slashes =True_, _redirect_class =HTTPPermanentRedirect_)[[source]](_modules/aiohttp/web_middlewares.html#normalize_path_middleware)¶
    

Middleware factory which produces a middleware that normalizes the path of a request. By normalizing it means:

>   * Add or remove a trailing slash to the path.
> 
>   * Double slashes are replaced by one.
> 
> 


The middleware returns as soon as it finds a path that resolves correctly. The order if both merge and append/remove are enabled is:

>   1. _merge_slashes_
> 
>   2. _append_slash_ or _remove_slash_
> 
>   3. both _merge_slashes_ and _append_slash_ or _remove_slash_
> 
> 


If the path resolves with at least one of those conditions, it will redirect to the new path.

Only one of _append_slash_ and _remove_slash_ can be enabled. If both are `True` the factory will raise an `AssertionError`

If _append_slash_ is `True` the middleware will append a slash when needed. If a resource is defined with trailing slash and the request comes without it, it will append it automatically.

If _remove_slash_ is `True`, _append_slash_ must be `False`. When enabled the middleware will remove trailing slashes and redirect if the resource is defined.

If _merge_slashes_ is `True`, merge multiple consecutive slashes in the path into one.

Added in version 3.4: Support for _remove_slash_

[ ](index.html)

# [aiohttp](index.html)

Async HTTP client/server for asyncio and Python

  * [ ](https://github.com/aio-libs/aiohttp/actions?query=workflow%3ACI)
  * [ ](https://codecov.io/github/aio-libs/aiohttp)
  * [ ](https://badge.fury.io/py/aiohttp)
  * [ ](https://gitter.im/aio-libs/Lobby) 


### Navigation

  * [Client](client.html)
  * [Server](web.html)
    * [Tutorial](https://demos.aiohttp.org)
    * [Quickstart](web_quickstart.html)
    * [Advanced Usage](web_advanced.html)
    * [Low Level](web_lowlevel.html)
    * Reference
    * [Logging](logging.html)
    * [Testing](testing.html)
    * [Deployment](deployment.html)
  * [Utilities](utilities.html)
  * [FAQ](faq.html)
  * [Miscellaneous](misc.html)
  * [Who uses aiohttp?](external.html)
  * [Contributing](contributing.html)
  * [Threat Model](threat_model.html)



### Quick search

(C)aiohttp contributors. | Powered by [Sphinx 9.0.4](http://sphinx-doc.org/) | [Page source](_sources/web_reference.rst.txt)

[ ](https://github.com/aio-libs/aiohttp)
  *[*]: Keyword-only parameters separator (PEP 3102)
