<!-- Source: https://docs.aiohttp.org/en/stable/web_advanced.html | Tier: A | Topic: aiohttp-security | Fetched: 2026-06-26 -->

# Web Server Advanced¶

## Unicode support¶

_aiohttp_ does [requoting](glossary.html#term-requoting) of incoming request path.

Unicode (non-ASCII) symbols are processed transparently on both _route adding_ and _resolving_ (internally everything is converted to [percent-encoding](glossary.html#term-percent-encoding) form by [yarl](glossary.html#term-yarl) library).

But in case of custom regular expressions for [Variable Resources](web_quickstart.html#aiohttp-web-variable-handler) please take care that URL is _percent encoded_ : if you pass Unicode patterns they don’t match to _requoted_ path.

## Peer disconnection¶

_aiohttp_ has 2 approaches to handling client disconnections. If you are familiar with asyncio, or scalability is a concern for your application, we recommend using the handler cancellation method.

### Raise on read/write (default)¶

When a client peer is gone, a subsequent reading or writing raises [`OSError`](https://docs.python.org/3/library/exceptions.html#OSError "\(in Python v3.14\)") or a more specific exception like [`ConnectionResetError`](https://docs.python.org/3/library/exceptions.html#ConnectionResetError "\(in Python v3.14\)").

This behavior is similar to classic WSGI frameworks like Flask and Django.

The reason for disconnection varies; it can be a network issue or explicit socket closing on the peer side without reading the full server response.

_aiohttp_ handles disconnection properly but you can handle it explicitly, e.g.:
    
    
    async def handler(request):
        try:
            text = await request.text()
        except OSError:
            # disconnected
    

### Web handler cancellation¶

This method can be enabled using the `handler_cancellation` parameter to [`run_app()`](web_reference.html#aiohttp.web.run_app "aiohttp.web.run_app").

When a client disconnects, the web handler task will be cancelled. This is recommended as it can reduce the load on your server when there is no client to receive a response. It can also help make your application more resilient to DoS attacks (by requiring an attacker to keep a connection open in order to waste server resources).

This behavior is very different from classic WSGI frameworks like Flask and Django. It requires a reasonable level of asyncio knowledge to use correctly without causing issues in your code. We provide some examples here to help understand the complexity and methods needed to deal with them.

Warning

[web-handler](glossary.html#term-web-handler) execution could be canceled on every `await` or `async with` if client drops connection without reading entire response’s BODY.

Sometimes it is a desirable behavior: on processing `GET` request the code might fetch data from a database or other web resource, the fetching is potentially slow.

Canceling this fetch is a good idea: the client dropped the connection already, so there is no reason to waste time and resources (memory etc) by getting data from a DB without any chance to send it back to the client.

But sometimes the cancellation is bad: on `POST` requests very often it is needed to save data to a DB regardless of connection closing.

Cancellation prevention could be implemented in several ways:

  * Applying [`aiojobs.aiohttp.shield()`](https://aiojobs.readthedocs.io/en/stable/api.html#aiojobs.aiohttp.shield "\(in aiojobs v1.4\)") to a coroutine that saves data.

  * Using [aiojobs](http://aiojobs.readthedocs.io/en/latest/) or another third party library to run a task in the background.




[`aiojobs.aiohttp.shield()`](https://aiojobs.readthedocs.io/en/stable/api.html#aiojobs.aiohttp.shield "\(in aiojobs v1.4\)") can work well. The only disadvantage is you need to split the web handler into two async functions: one for the handler itself and another for protected code.

Warning

We don’t recommend using [`asyncio.shield()`](https://docs.python.org/3/library/asyncio-task.html#asyncio.shield "\(in Python v3.14\)") for this because the shielded task cannot be tracked by the application and therefore there is a risk that the task will get cancelled during application shutdown. The function provided by [aiojobs](http://aiojobs.readthedocs.io/en/latest/) operates in the same way except the inner task will be tracked by the Scheduler and will get waited on during the cleanup phase.

For example the following snippet is not safe:
    
    
    from aiojobs.aiohttp import shield
    
    async def handler(request):
        await shield(request, write_to_redis(request))
        await shield(request, write_to_postgres(request))
        return web.Response(text="OK")
    

Cancellation might occur while saving data in REDIS, so the `write_to_postgres` function will not be called, potentially leaving your data in an inconsistent state.

Instead, you would need to write something like:
    
    
    async def write_data(request):
        await write_to_redis(request)
        await write_to_postgres(request)
    
    async def handler(request):
        await shield(request, write_data(request))
        return web.Response(text="OK")
    

Alternatively, if you want to spawn a task without waiting for its completion, you can use [aiojobs](http://aiojobs.readthedocs.io/en/latest/) which provides an API for spawning new background jobs. It stores all scheduled activity in internal data structures and can terminate them gracefully:
    
    
    from aiojobs.aiohttp import setup, spawn
    
    async def handler(request):
        await spawn(request, write_data())
        return web.Response()
    
    app = web.Application()
    setup(app)
    app.router.add_get("/", handler)
    

Warning

Don’t use [`asyncio.create_task()`](https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task "\(in Python v3.14\)") for this. All tasks should be awaited at some point in your code (`aiojobs` handles this for you), otherwise you will hide legitimate exceptions and result in warnings being emitted.

A good case for using [`asyncio.create_task()`](https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task "\(in Python v3.14\)") is when you want to run something while you are processing other data, but still want to ensure the task is complete before returning:
    
    
    async def handler(request):
        t = asyncio.create_task(get_some_data())
        ...  # Do some other things, while data is being fetched.
        data = await t
        return web.Response(text=data)
    

One more approach would be to use [`aiojobs.aiohttp.atomic()`](https://aiojobs.readthedocs.io/en/stable/api.html#aiojobs.aiohttp.atomic "\(in aiojobs v1.4\)") decorator to execute the entire handler as a new job. Essentially restoring the default disconnection behavior only for specific handlers:
    
    
    from aiojobs.aiohttp import atomic
    
    @atomic
    async def handler(request):
        await write_to_db()
        return web.Response()
    
    app = web.Application()
    setup(app)
    app.router.add_post("/", handler)
    

It prevents all of the `handler` async function from cancellation, so `write_to_db` will never be interrupted.

## Passing a coroutine into run_app and Gunicorn¶

[`run_app()`](web_reference.html#aiohttp.web.run_app "aiohttp.web.run_app") accepts either application instance or a coroutine for making an application. The coroutine based approach allows to perform async IO before making an app:
    
    
    async def app_factory():
        await pre_init()
        app = web.Application()
        app.router.add_get(...)
        return app
    
    web.run_app(app_factory())
    

Gunicorn worker supports a factory as well. For Gunicorn the factory should accept zero parameters:
    
    
    async def my_web_app():
        app = web.Application()
        app.router.add_get(...)
        return app
    

Start gunicorn:
    
    
    $ gunicorn my_app_module:my_web_app --bind localhost:8080 --worker-class aiohttp.GunicornWebWorker
    

Added in version 3.1.

## Custom Routing Criteria¶

Sometimes you need to register [handlers](web_quickstart.html#aiohttp-web-handler) on more complex criteria than simply a _HTTP method_ and _path_ pair.

Although [`UrlDispatcher`](web_reference.html#aiohttp.web.UrlDispatcher "aiohttp.web.UrlDispatcher") does not support any extra criteria, routing based on custom conditions can be accomplished by implementing a second layer of routing in your application.

The following example shows custom routing based on the _HTTP Accept_ header:
    
    
    class AcceptChooser:
    
        def __init__(self):
            self._accepts = {}
    
        async def do_route(self, request):
            for accept in request.headers.getall('ACCEPT', []):
                acceptor = self._accepts.get(accept)
                if acceptor is not None:
                    return (await acceptor(request))
            raise HTTPNotAcceptable()
    
        def reg_acceptor(self, accept, handler):
            self._accepts[accept] = handler
    
    
    async def handle_json(request):
        # do json handling
    
    async def handle_xml(request):
        # do xml handling
    
    chooser = AcceptChooser()
    app.add_routes([web.get('/', chooser.do_route)])
    
    chooser.reg_acceptor('application/json', handle_json)
    chooser.reg_acceptor('application/xml', handle_xml)
    

## Static file handling¶

The best way to handle static files (images, JavaScripts, CSS files etc.) is using [Reverse Proxy](https://en.wikipedia.org/wiki/Reverse_proxy) like [nginx](https://nginx.org/) or [CDN](https://en.wikipedia.org/wiki/Content_delivery_network) services.

But for development it’s very convenient to handle static files by aiohttp server itself.

To do it just register a new static route by [`RouteTableDef.static()`](web_reference.html#aiohttp.web.RouteTableDef.static "aiohttp.web.RouteTableDef.static") or [`static()`](web_reference.html#aiohttp.web.static "aiohttp.web.static") calls:
    
    
    app.add_routes([web.static('/prefix', path_to_static_folder)])
    
    routes.static('/prefix', path_to_static_folder)
    

When a directory is accessed within a static route then the server responses to client with `HTTP/403 Forbidden` by default. Displaying folder index instead could be enabled with `show_index` parameter set to `True`:
    
    
    web.static('/prefix', path_to_static_folder, show_index=True)
    

When a symlink that leads outside the static directory is accessed, the server responds to the client with `HTTP/404 Not Found` by default. To allow the server to follow symlinks that lead outside the static root, the parameter `follow_symlinks` should be set to `True`:
    
    
    web.static('/prefix', path_to_static_folder, follow_symlinks=True)
    

Caution

Enabling `follow_symlinks` can be a security risk, and may lead to a directory transversal attack. You do NOT need this option to follow symlinks which point to somewhere else within the static directory, this option is only used to break out of the security sandbox. Enabling this option is highly discouraged, and only expected to be used for edge cases in a local development setting where remote users do not have access to the server.

When you want to enable cache busting, parameter `append_version` can be set to `True`

Cache busting is the process of appending some form of file version hash to the filename of resources like JavaScript and CSS files. The performance advantage of doing this is that we can tell the browser to cache these files indefinitely without worrying about the client not getting the latest version when the file changes:
    
    
    web.static('/prefix', path_to_static_folder, append_version=True)
    

## Template Rendering¶

[`aiohttp.web`](web.html#module-aiohttp.web "aiohttp.web") does not support template rendering out-of-the-box.

However, there is a third-party library, [`aiohttp_jinja2`](https://aiohttp-jinja2.readthedocs.io/en/stable/api.html#module-aiohttp_jinja2 "\(in aiohttp_jinja2 v1.5\)"), which is supported by the _aiohttp_ authors.

Using it is rather simple. First, setup a _jinja2 environment_ with a call to [`aiohttp_jinja2.setup()`](https://aiohttp-jinja2.readthedocs.io/en/stable/api.html#aiohttp_jinja2.setup "\(in aiohttp_jinja2 v1.5\)"):
    
    
    app = web.Application()
    aiohttp_jinja2.setup(app,
        loader=jinja2.FileSystemLoader('/path/to/templates/folder'))
    

After that you may use the template engine in your [handlers](web_quickstart.html#aiohttp-web-handler). The most convenient way is to simply wrap your handlers with the [`aiohttp_jinja2.template()`](https://aiohttp-jinja2.readthedocs.io/en/stable/api.html#aiohttp_jinja2.template "\(in aiohttp_jinja2 v1.5\)") decorator:
    
    
    @aiohttp_jinja2.template('tmpl.jinja2')
    async def handler(request):
        return {'name': 'Andrew', 'surname': 'Svetlov'}
    

If you prefer the [Mako](http://www.makotemplates.org/) template engine, please take a look at the [aiohttp_mako](https://github.com/aio-libs/aiohttp_mako) library.

Warning

[`aiohttp_jinja2.template()`](https://aiohttp-jinja2.readthedocs.io/en/stable/api.html#aiohttp_jinja2.template "\(in aiohttp_jinja2 v1.5\)") should be applied **before** [`RouteTableDef.get()`](web_reference.html#aiohttp.web.RouteTableDef.get "aiohttp.web.RouteTableDef.get") decorator and family, e.g. it must be the _first_ (most _down_ decorator in the chain):
    
    
    @routes.get('/path')
    @aiohttp_jinja2.template('tmpl.jinja2')
    async def handler(request):
        return {'name': 'Andrew', 'surname': 'Svetlov'}
    

## Reading from the same task in WebSockets¶

Reading from the _WebSocket_ (`await ws.receive()`) **must only** be done inside the request handler _task_ ; however, writing (`ws.send_str(...)`) to the _WebSocket_ , closing (`await ws.close()`) and canceling the handler task may be delegated to other tasks. See also [FAQ section](faq.html#aiohttp-faq-terminating-websockets).

[`aiohttp.web`](web.html#module-aiohttp.web "aiohttp.web") creates an implicit [`asyncio.Task`](https://docs.python.org/3/library/asyncio-task.html#asyncio.Task "\(in Python v3.14\)") for handling every incoming request.

Note

While [`aiohttp.web`](web.html#module-aiohttp.web "aiohttp.web") itself only supports _WebSockets_ without downgrading to _LONG-POLLING_ , etc., our team supports [SockJS](https://github.com/aio-libs/sockjs), an aiohttp-based library for implementing SockJS-compatible server code.

Warning

Parallel reads from websocket are forbidden, there is no possibility to call [`WebSocketResponse.receive()`](web_reference.html#aiohttp.web.WebSocketResponse.receive "aiohttp.web.WebSocketResponse.receive") from two tasks.

See [FAQ section](faq.html#aiohttp-faq-parallel-event-sources) for instructions how to solve the problem.

## Data Sharing aka No Singletons Please¶

[`aiohttp.web`](web.html#module-aiohttp.web "aiohttp.web") discourages the use of _global variables_ , aka _singletons_. Every variable should have its own context that is _not global_.

Global variables are generally considered bad practice due to the complexity they add in keeping track of state changes to variables.

_aiohttp_ does not use globals by design, which will reduce the number of bugs and/or unexpected behaviors for its users. For example, an i18n translated string being written for one request and then being served to another.

So, [`Application`](web_reference.html#aiohttp.web.Application "aiohttp.web.Application") and [`Request`](web_reference.html#aiohttp.web.Request "aiohttp.web.Request") support a [`collections.abc.MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping "\(in Python v3.14\)") interface (i.e. they are dict-like objects), allowing them to be used as data stores.

### Application’s config¶

For storing _global-like_ variables, feel free to save them in an [`Application`](web_reference.html#aiohttp.web.Application "aiohttp.web.Application") instance:
    
    
    app['my_private_key'] = data
    

and get it back in the [web-handler](glossary.html#term-web-handler):
    
    
    async def handler(request):
        data = request.app['my_private_key']
    

Rather than using [`str`](https://docs.python.org/3/library/stdtypes.html#str "\(in Python v3.14\)") keys, we recommend using [`AppKey`](web_reference.html#aiohttp.web.AppKey "aiohttp.web.AppKey"). This is required for type safety (e.g. when checking with mypy):
    
    
    my_private_key = web.AppKey("my_private_key", str)
    app[my_private_key] = data
    
    async def handler(request: web.Request):
        data = request.app[my_private_key]
        # reveal_type(data) -> str
    

In case of nested applications the desired lookup strategy could be the following:

  1. Search the key in the current nested application.

  2. If the key is not found continue searching in the parent application(s).




For this please use [`Request.config_dict`](web_reference.html#aiohttp.web.Request.config_dict "aiohttp.web.Request.config_dict") read-only property:
    
    
    async def handler(request):
        data = request.config_dict[my_private_key]
    

The app object can be used in this way to reuse a database connection or anything else needed throughout the application.

See this reference section for more detail: [Application and Router](web_reference.html#aiohttp-web-app-and-router).

### Request’s storage¶

Variables that are only needed for the lifetime of a [`Request`](web_reference.html#aiohttp.web.Request "aiohttp.web.Request"), can be stored in a [`Request`](web_reference.html#aiohttp.web.Request "aiohttp.web.Request"). Similarly to [`Application`](web_reference.html#aiohttp.web.Application "aiohttp.web.Application"), [`RequestKey`](web_reference.html#aiohttp.web.RequestKey "aiohttp.web.RequestKey") instances or strings can be used as keys:
    
    
    my_private_key = web.RequestKey("my_private_key", str)
    
    async def handler(request):
      request[my_private_key] = "data"
      ...
    

This is mostly useful for Middlewares and Signals handlers to store data for further processing by the next handlers in the chain.

### Response’s storage¶

[`StreamResponse`](web_reference.html#aiohttp.web.StreamResponse "aiohttp.web.StreamResponse") and [`Response`](web_reference.html#aiohttp.web.Response "aiohttp.web.Response") objects also support [`collections.abc.MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping "\(in Python v3.14\)") interface. This is useful when you want to share data with signals and middlewares once all the work in the handler is done:
    
    
    my_metric_key = web.ResponseKey("my_metric_key", int)
    
    async def handler(request):
      [ do all the work ]
      response[my_metric_key] = 123
      return response
    

### Naming hint¶

To avoid clashing with other _aiohttp_ users and third-party libraries, please choose a unique key name for storing data.

If your code is published on PyPI, then the project name is most likely unique and safe to use as the key. Otherwise, something based on your company name/url would be satisfactory (i.e. `org.company.app`).

## ContextVars support¶

Asyncio has [`Context Variables`](https://docs.python.org/3/library/contextvars.html#module-contextvars "\(in Python v3.14\)") as a context-local storage (a generalization of thread-local concept that works with asyncio tasks also).

_aiohttp_ server supports it in the following way:

  * A server inherits the current task’s context used when creating it. [`aiohttp.web.run_app()`](web_reference.html#aiohttp.web.run_app "aiohttp.web.run_app") runs a task for handling all underlying jobs running the app, but alternatively Application runners can be used.

  * Application initialization / finalization events ([`Application.cleanup_ctx`](web_reference.html#aiohttp.web.Application.cleanup_ctx "aiohttp.web.Application.cleanup_ctx"), [`Application.on_startup`](web_reference.html#aiohttp.web.Application.on_startup "aiohttp.web.Application.on_startup") and [`Application.on_shutdown`](web_reference.html#aiohttp.web.Application.on_shutdown "aiohttp.web.Application.on_shutdown"), [`Application.on_cleanup`](web_reference.html#aiohttp.web.Application.on_cleanup "aiohttp.web.Application.on_cleanup")) are executed inside the same context.

E.g. all context modifications made on application startup are visible on teardown.

  * On every request handling _aiohttp_ creates a context copy. [web-handler](glossary.html#term-web-handler) has all variables installed on initialization stage. But the context modification made by a handler or middleware is invisible to another HTTP request handling call.




An example of context vars usage:
    
    
    from contextvars import ContextVar
    
    from aiohttp import web
    
    VAR = ContextVar('VAR', default='default')
    
    
    async def coro():
        return VAR.get()
    
    
    async def handler(request):
        var = VAR.get()
        VAR.set('handler')
        ret = await coro()
        return web.Response(text='\n'.join([var,
                                            ret]))
    
    
    async def on_startup(app):
        print('on_startup', VAR.get())
        VAR.set('on_startup')
    
    
    async def on_cleanup(app):
        print('on_cleanup', VAR.get())
        VAR.set('on_cleanup')
    
    
    async def init():
        print('init', VAR.get())
        VAR.set('init')
        app = web.Application()
        app.router.add_get('/', handler)
    
        app.on_startup.append(on_startup)
        app.on_cleanup.append(on_cleanup)
        return app
    
    
    web.run_app(init())
    print('done', VAR.get())
    

Added in version 3.5.

## Middlewares¶

[`aiohttp.web`](web.html#module-aiohttp.web "aiohttp.web") provides a powerful mechanism for customizing [request handlers](web_quickstart.html#aiohttp-web-handler) via _middlewares_.

A _middleware_ is a coroutine that can modify either the request or response. For example, here’s a simple _middleware_ which appends `' wink'` to the response:
    
    
    from aiohttp import web
    from typing import Callable, Awaitable
    
    @web.middleware
    async def middleware(
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
    ) -> web.StreamResponse:
        resp = await handler(request)
        resp.text = resp.text + ' wink'
        return resp
    

Note

The example won’t work with streamed responses or websockets

Every _middleware_ should accept two parameters, a [`request`](web_reference.html#aiohttp.web.Request "aiohttp.web.Request") instance and a _handler_ , and return the response or raise an exception. If the exception is not an instance of [`HTTPException`](web_reference.html#aiohttp.web.HTTPException "aiohttp.web.HTTPException") it is converted to `500` `HTTPInternalServerError` after processing the middlewares chain.

Warning

Second argument should be named _handler_ exactly.

When creating an [`Application`](web_reference.html#aiohttp.web.Application "aiohttp.web.Application"), these _middlewares_ are passed to the keyword-only `middlewares` parameter:
    
    
    app = web.Application(middlewares=[middleware_1,
                                       middleware_2])
    

Internally, a single [request handler](web_quickstart.html#aiohttp-web-handler) is constructed by applying the middleware chain to the original handler in reverse order, and is called by the `RequestHandler` as a regular _handler_.

Since _middlewares_ are themselves coroutines, they may perform extra `await` calls when creating a new handler, e.g. call database etc.

_Middlewares_ usually call the handler, but they may choose to ignore it, e.g. displaying _403 Forbidden page_ or raising `HTTPForbidden` exception if the user does not have permissions to access the underlying resource. They may also render errors raised by the handler, perform some pre- or post-processing like handling _CORS_ and so on.

The following code demonstrates middlewares execution order:
    
    
    from aiohttp import web
    from typing import Callable, Awaitable
    
    async def test(request: web.Request) -> web.Response:
        print('Handler function called')
        return web.Response(text="Hello")
    
    @web.middleware
    async def middleware1(
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
    ) -> web.StreamResponse:
        print('Middleware 1 called')
        response = await handler(request)
        print('Middleware 1 finished')
        return response
    
    @web.middleware
    async def middleware2(
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
    ) -> web.StreamResponse:
        print('Middleware 2 called')
        response = await handler(request)
        print('Middleware 2 finished')
        return response
    
    
    app = web.Application(middlewares=[middleware1, middleware2])
    app.router.add_get('/', test)
    web.run_app(app)
    

Produced output:
    
    
    Middleware 1 called
    Middleware 2 called
    Handler function called
    Middleware 2 finished
    Middleware 1 finished
    

### Request Body Stream Consumption¶

Warning

When middleware reads the request body (using [`read()`](web_reference.html#aiohttp.web.BaseRequest.read "aiohttp.web.BaseRequest.read"), [`text()`](web_reference.html#aiohttp.web.BaseRequest.text "aiohttp.web.BaseRequest.text"), [`json()`](web_reference.html#aiohttp.web.BaseRequest.json "aiohttp.web.BaseRequest.json"), or [`post()`](web_reference.html#aiohttp.web.BaseRequest.post "aiohttp.web.BaseRequest.post")), the body stream is consumed. However, these high-level methods cache their result, so subsequent calls from the handler or other middleware will return the same cached value.

The important distinction is:

  * High-level methods ([`read()`](web_reference.html#aiohttp.web.BaseRequest.read "aiohttp.web.BaseRequest.read"), [`text()`](web_reference.html#aiohttp.web.BaseRequest.text "aiohttp.web.BaseRequest.text"), [`json()`](web_reference.html#aiohttp.web.BaseRequest.json "aiohttp.web.BaseRequest.json"), [`post()`](web_reference.html#aiohttp.web.BaseRequest.post "aiohttp.web.BaseRequest.post")) cache their results internally, so they can be called multiple times and will return the same value.

  * Direct stream access via [`content`](web_reference.html#aiohttp.web.BaseRequest.content "aiohttp.web.BaseRequest.content") does NOT have this caching behavior. Once you read from `request.content` directly (e.g., using `await request.content.read()`), subsequent reads will return empty bytes.




Consider this middleware that logs request bodies:
    
    
    from aiohttp import web
    from typing import Callable, Awaitable
    
    async def logging_middleware(
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
    ) -> web.StreamResponse:
        # This consumes the request body stream
        body = await request.text()
        print(f"Request body: {body}")
        return await handler(request)
    
    async def handler(request: web.Request) -> web.Response:
        # This will return the same value that was read in the middleware
        # (i.e., the cached result, not an empty string)
        body = await request.text()
        return web.Response(text=f"Received: {body}")
    

In contrast, when accessing the stream directly (not recommended in middleware):
    
    
    async def stream_middleware(
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
    ) -> web.StreamResponse:
        # Reading directly from the stream - this consumes it!
        data = await request.content.read()
        print(f"Stream data: {data}")
        return await handler(request)
    
    async def handler(request: web.Request) -> web.Response:
        # This will return empty bytes because the stream was already consumed
        data = await request.content.read()
        # data will be b'' (empty bytes)
    
        # However, high-level methods would still work if called for the first time:
        # body = await request.text()  # This would read from internal cache if available
        return web.Response(text=f"Received: {data}")
    

When working with raw stream data that needs to be shared between middleware and handlers:
    
    
    raw_body_key = web.RequestKey("raw_body_key", bytes)
    
    async def stream_parsing_middleware(
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
    ) -> web.StreamResponse:
        # Read stream once and store the data
        raw_data = await request.content.read()
        request[raw_body_key] = raw_data
        return await handler(request)
    
    async def handler(request: web.Request) -> web.Response:
        # Access the stored data instead of reading the stream again
        raw_data = request.get(raw_body_key, b'')
        return web.Response(body=raw_data)
    

### Example¶

A common use of middlewares is to implement custom error pages. The following example will render 404 errors using a JSON response, as might be appropriate a JSON REST service:
    
    
    from aiohttp import web
    
    @web.middleware
    async def error_middleware(request, handler):
        try:
            response = await handler(request)
            if response.status != 404:
                return response
            message = response.message
        except web.HTTPException as ex:
            if ex.status != 404:
                raise
            message = ex.reason
        return web.json_response({'error': message})
    
    app = web.Application(middlewares=[error_middleware])
    

### Middleware Factory¶

A _middleware factory_ is a function that creates a middleware with passed arguments. For example, here’s a trivial _middleware factory_ :
    
    
    def middleware_factory(text):
        @middleware
        async def sample_middleware(request, handler):
            resp = await handler(request)
            resp.text = resp.text + text
            return resp
        return sample_middleware
    

Remember that contrary to regular middlewares you need the result of a middleware factory not the function itself. So when passing a middleware factory to an app you actually need to call it:
    
    
    app = web.Application(middlewares=[middleware_factory(' wink')])
    

## Signals¶

Although middlewares can customize [request handlers](web_quickstart.html#aiohttp-web-handler) before or after a [`Response`](web_reference.html#aiohttp.web.Response "aiohttp.web.Response") has been prepared, they can’t customize a [`Response`](web_reference.html#aiohttp.web.Response "aiohttp.web.Response") **while** it’s being prepared. For this [`aiohttp.web`](web.html#module-aiohttp.web "aiohttp.web") provides _signals_.

For example, a middleware can only change HTTP headers for _unprepared_ responses (see [`StreamResponse.prepare()`](web_reference.html#aiohttp.web.StreamResponse.prepare "aiohttp.web.StreamResponse.prepare")), but sometimes we need a hook for changing HTTP headers for streamed responses and WebSockets. This can be accomplished by subscribing to the [`Application.on_response_prepare`](web_reference.html#aiohttp.web.Application.on_response_prepare "aiohttp.web.Application.on_response_prepare") signal, which is called after default headers have been computed and directly before headers are sent:
    
    
    async def on_prepare(request, response):
        response.headers['My-Header'] = 'value'
    
    app.on_response_prepare.append(on_prepare)
    

Additionally, the [`Application.on_startup`](web_reference.html#aiohttp.web.Application.on_startup "aiohttp.web.Application.on_startup") and [`Application.on_cleanup`](web_reference.html#aiohttp.web.Application.on_cleanup "aiohttp.web.Application.on_cleanup") signals can be subscribed to for application component setup and tear down accordingly.

The following example will properly initialize and dispose an asyncpg connection engine:
    
    
    from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
    
    pg_engine = web.AppKey("pg_engine", AsyncEngine)
    
    async def create_pg(app):
        app[pg_engine] = await create_async_engine(
            "postgresql+asyncpg://postgre:@localhost:5432/postgre"
        )
    
    async def dispose_pg(app):
        await app[pg_engine].dispose()
    
    app.on_startup.append(create_pg)
    app.on_cleanup.append(dispose_pg)
    

Signal handlers should not return a value but may modify incoming mutable parameters.

Signal handlers will be run sequentially, in order they were added. All handlers must be asynchronous since _aiohttp_ 3.0.

## Cleanup Context¶

Bare [`Application.on_startup`](web_reference.html#aiohttp.web.Application.on_startup "aiohttp.web.Application.on_startup") / [`Application.on_cleanup`](web_reference.html#aiohttp.web.Application.on_cleanup "aiohttp.web.Application.on_cleanup") pair still has a pitfall: signals handlers are independent on each other.

E.g. we have `[create_pg, create_redis]` in _startup_ signal and `[dispose_pg, dispose_redis]` in _cleanup_.

If, for example, `create_pg(app)` call fails `create_redis(app)` is not called. But on application cleanup both `dispose_pg(app)` and `dispose_redis(app)` are still called: _cleanup signal_ has no knowledge about startup/cleanup pairs and their execution state.

The solution is [`Application.cleanup_ctx`](web_reference.html#aiohttp.web.Application.cleanup_ctx "aiohttp.web.Application.cleanup_ctx") usage:
    
    
    @contextlib.asynccontextmanager
    async def pg_engine(app: web.Application):
        app[pg_engine] = await create_async_engine(
            "postgresql+asyncpg://postgre:@localhost:5432/postgre"
        )
        yield
        await app[pg_engine].dispose()
    
    app.cleanup_ctx.append(pg_engine)
    

The attribute is a list of _asynchronous generators_ , a code _before_ `yield` is an initialization stage (called on _startup_), a code _after_ `yield` is executed on _cleanup_. The generator must have only one `yield`.

_aiohttp_ guarantees that _cleanup code_ is called if and only if _startup code_ was successfully finished.

Added in version 3.1.

## Nested applications¶

Sub applications are designed for solving the problem of the big monolithic code base. Let’s assume we have a project with own business logic and tools like administration panel and debug toolbar.

Administration panel is a separate application by its own nature but all toolbar URLs are served by prefix like `/admin`.

Thus we’ll create a totally separate application named `admin` and connect it to main app with prefix by [`Application.add_subapp()`](web_reference.html#aiohttp.web.Application.add_subapp "aiohttp.web.Application.add_subapp"):
    
    
    admin = web.Application()
    # setup admin routes, signals and middlewares
    
    app.add_subapp('/admin/', admin)
    

Middlewares and signals from `app` and `admin` are chained.

It means that if URL is `'/admin/something'` middlewares from `app` are applied first and `admin.middlewares` are the next in the call chain.

The same is going for [`Application.on_response_prepare`](web_reference.html#aiohttp.web.Application.on_response_prepare "aiohttp.web.Application.on_response_prepare") signal – the signal is delivered to both top level `app` and `admin` if processing URL is routed to `admin` sub-application.

Common signals like [`Application.on_startup`](web_reference.html#aiohttp.web.Application.on_startup "aiohttp.web.Application.on_startup"), [`Application.on_shutdown`](web_reference.html#aiohttp.web.Application.on_shutdown "aiohttp.web.Application.on_shutdown") and [`Application.on_cleanup`](web_reference.html#aiohttp.web.Application.on_cleanup "aiohttp.web.Application.on_cleanup") are delivered to all registered sub-applications. The passed parameter is sub-application instance, not top-level application.

Third level sub-applications can be nested into second level ones – there are no limitation for nesting level.

Url reversing for sub-applications should generate urls with proper prefix.

But for getting URL sub-application’s router should be used:
    
    
    admin = web.Application()
    admin.add_routes([web.get('/resource', handler, name='name')])
    
    app.add_subapp('/admin/', admin)
    
    url = admin.router['name'].url_for()
    

The generated `url` from example will have a value `URL('/admin/resource')`.

If main application should do URL reversing for sub-application it could use the following explicit technique:
    
    
    admin = web.Application()
    admin_key = web.AppKey('admin_key', web.Application)
    admin.add_routes([web.get('/resource', handler, name='name')])
    
    app.add_subapp('/admin/', admin)
    app[admin_key] = admin
    
    async def handler(request: web.Request):  # main application's handler
        admin = request.app[admin_key]
        url = admin.router['name'].url_for()
    

## _Expect_ Header¶

[`aiohttp.web`](web.html#module-aiohttp.web "aiohttp.web") supports _Expect_ header. By default it sends `HTTP/1.1 100 Continue` line to client, or raises `HTTPExpectationFailed` if header value is not equal to “100-continue”. It is possible to specify custom _Expect_ header handler on per route basis. This handler gets called if _Expect_ header exist in request after receiving all headers and before processing application’s Middlewares and route handler. Handler can return _None_ , in that case the request processing continues as usual. If handler returns an instance of class [`StreamResponse`](web_reference.html#aiohttp.web.StreamResponse "aiohttp.web.StreamResponse"), _request handler_ uses it as response. Also handler can raise a subclass of [`HTTPException`](web_reference.html#aiohttp.web.HTTPException "aiohttp.web.HTTPException"). In this case all further processing will not happen and client will receive appropriate http response.

Note

A server that does not understand or is unable to comply with any of the expectation values in the Expect field of a request MUST respond with appropriate error status. The server MUST respond with a 417 (Expectation Failed) status if any of the expectations cannot be met or, if there are other problems with the request, some other 4xx status.

<http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.20>

If all checks pass, the custom handler _must_ write a _HTTP/1.1 100 Continue_ status code before returning.

The following example shows how to setup a custom handler for the _Expect_ header:
    
    
    async def check_auth(request):
        if request.version != aiohttp.HttpVersion11:
            return
    
        if request.headers.get('EXPECT') != '100-continue':
            raise HTTPExpectationFailed(text="Unknown Expect: %s" % expect)
    
        if request.headers.get('AUTHORIZATION') is None:
            raise HTTPForbidden()
    
        request.transport.write(b"HTTP/1.1 100 Continue\r\n\r\n")
    
    async def hello(request):
        return web.Response(body=b"Hello, world")
    
    app = web.Application()
    app.add_routes([web.add_get('/', hello, expect_handler=check_auth)])
    

## Custom resource implementation¶

To register custom resource use `register_resource()`. Resource instance must implement AbstractResource interface.

## Application runners¶

[`run_app()`](web_reference.html#aiohttp.web.run_app "aiohttp.web.run_app") provides a simple _blocking_ API for running an [`Application`](web_reference.html#aiohttp.web.Application "aiohttp.web.Application").

For starting the application _asynchronously_ or serving on multiple HOST/PORT [`AppRunner`](web_reference.html#aiohttp.web.AppRunner "aiohttp.web.AppRunner") exists.

The simple startup code for serving HTTP site on `'localhost'`, port `8080` looks like:
    
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8080)
    await site.start()
    
    while True:
        await asyncio.sleep(3600)  # sleep forever
    

To stop serving call [`AppRunner.cleanup()`](web_reference.html#aiohttp.web.AppRunner.cleanup "aiohttp.web.AppRunner.cleanup"):
    
    
    await runner.cleanup()
    

Added in version 3.0.

## Graceful shutdown¶

Stopping _aiohttp web server_ by just closing all connections is not always satisfactory.

When aiohttp is run with [`run_app()`](web_reference.html#aiohttp.web.run_app "aiohttp.web.run_app"), it will attempt a graceful shutdown by following these steps (if using a runner, then calling [`AppRunner.cleanup()`](web_reference.html#aiohttp.web.AppRunner.cleanup "aiohttp.web.AppRunner.cleanup") will perform these steps, excluding step 7).

  1. Stop each site listening on sockets, so new connections will be rejected.

  2. Close idle keep-alive connections (and set active ones to close upon completion).

  3. Call the [`Application.on_shutdown`](web_reference.html#aiohttp.web.Application.on_shutdown "aiohttp.web.Application.on_shutdown") signal. This should be used to shutdown long-lived connections, such as websockets (see below).

  4. Wait a short time for running handlers to complete. This allows any pending handlers to complete successfully. The timeout can be adjusted with `shutdown_timeout` in [`run_app()`](web_reference.html#aiohttp.web.run_app "aiohttp.web.run_app").

  5. Close any remaining connections and cancel their handlers. It will wait on the canceling handlers for a short time, again adjustable with `shutdown_timeout`.

  6. Call the [`Application.on_cleanup`](web_reference.html#aiohttp.web.Application.on_cleanup "aiohttp.web.Application.on_cleanup") signal. This should be used to cleanup any resources (such as DB connections). This includes completing the cleanup contexts which may be used to ensure background tasks are completed successfully (see handler cancellation or [aiojobs](http://aiojobs.readthedocs.io/en/latest/) for examples).

  7. Cancel any remaining tasks and wait on them to complete.




### Websocket shutdown¶

One problem is if the application supports [websockets](glossary.html#term-websocket) or _data streaming_ it most likely has open connections at server shutdown time.

The _library_ has no knowledge how to close them gracefully but a developer can help by registering an [`Application.on_shutdown`](web_reference.html#aiohttp.web.Application.on_shutdown "aiohttp.web.Application.on_shutdown") signal handler.

A developer should keep a list of opened connections ([`Application`](web_reference.html#aiohttp.web.Application "aiohttp.web.Application") is a good candidate).

The following [websocket](glossary.html#term-websocket) snippet shows an example of a websocket handler:
    
    
    from aiohttp import web
    import weakref
    
    app = web.Application()
    websockets = web.AppKey("websockets", weakref.WeakSet)
    app[websockets] = weakref.WeakSet()
    
    async def websocket_handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
    
        request.app[websockets].add(ws)
        try:
            async for msg in ws:
                ...
        finally:
            request.app[websockets].discard(ws)
    
        return ws
    

Then the signal handler may look like:
    
    
    from aiohttp import WSCloseCode
    
    async def on_shutdown(app):
        for ws in set(app[websockets]):
            await ws.close(code=WSCloseCode.GOING_AWAY, message="Server shutdown")
    
    app.on_shutdown.append(on_shutdown)
    

## Ceil of absolute timeout value¶

_aiohttp_ **ceils** internal timeout values if the value is equal or greater than 5 seconds. The timeout expires at the next integer second greater than `current_time + timeout`.

More details about ceiling absolute timeout values is available here [Timeouts](client_quickstart.html#aiohttp-client-timeouts).

The default threshold can be configured at [`aiohttp.web.Application`](web_reference.html#aiohttp.web.Application "aiohttp.web.Application") level using the `handler_args` parameter.
    
    
    app = web.Application(handler_args={"timeout_ceil_threshold": 1})
    

## Background tasks¶

Sometimes there’s a need to perform some asynchronous operations just after application start-up.

Even more, in some sophisticated systems there could be a need to run some background tasks in the event loop along with the application’s request handler. Such as listening to message queue or other network message/event sources (e.g. ZeroMQ, Redis Pub/Sub, AMQP, etc.) to react to received messages within the application.

For example the background task could listen to ZeroMQ on `zmq.SUB` socket, process and forward retrieved messages to clients connected via WebSocket that are stored somewhere in the application (e.g. in the `application['websockets']` list).

To run such short and long running background tasks aiohttp provides an ability to register [`Application.on_startup`](web_reference.html#aiohttp.web.Application.on_startup "aiohttp.web.Application.on_startup") signal handler(s) that will run along with the application’s request handler.

For example there’s a need to run one quick task and two long running tasks that will live till the application is alive. The appropriate background tasks could be registered as an [`Application.on_startup`](web_reference.html#aiohttp.web.Application.on_startup "aiohttp.web.Application.on_startup") signal handler or [`Application.cleanup_ctx`](web_reference.html#aiohttp.web.Application.cleanup_ctx "aiohttp.web.Application.cleanup_ctx") as shown in the example below:
    
    
    async def listen_to_redis(app: web.Application):
        client = redis.from_url("redis://localhost:6379")
        channel = "news"
        async with client.pubsub() as pubsub:
            await pubsub.subscribe(channel)
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True)
                if msg is not None:
                    for ws in app["websockets"]:
                        await ws.send_str("{}: {}".format(channel, msg))
    
    
    @contextlib.asynccontextmanager
    async def background_tasks(app):
        app[redis_listener] = asyncio.create_task(listen_to_redis(app))
    
        yield
    
        app[redis_listener].cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await app[redis_listener]
    
    
    app = web.Application()
    redis_listener = web.AppKey("redis_listener", asyncio.Task[None])
    app.cleanup_ctx.append(background_tasks)
    web.run_app(app)
    

The task `listen_to_redis` will run forever. To shut it down correctly [`Application.on_cleanup`](web_reference.html#aiohttp.web.Application.on_cleanup "aiohttp.web.Application.on_cleanup") signal handler may be used to send a cancellation to it.

### Complex Applications¶

Sometimes aiohttp is not the sole part of an application and additional tasks/processes may need to be run alongside the aiohttp [`Application`](web_reference.html#aiohttp.web.Application "aiohttp.web.Application").

Generally, the best way to achieve this is to use [`aiohttp.web.run_app()`](web_reference.html#aiohttp.web.run_app "aiohttp.web.run_app") as the entry point for the program. Other tasks can then be run via [`Application.startup`](web_reference.html#aiohttp.web.Application.startup "aiohttp.web.Application.startup") and [`Application.on_cleanup`](web_reference.html#aiohttp.web.Application.on_cleanup "aiohttp.web.Application.on_cleanup"). By having the [`Application`](web_reference.html#aiohttp.web.Application "aiohttp.web.Application") control the lifecycle of the entire program, the code will be more robust and ensure that the tasks are started and stopped along with the application.

For example, running a long-lived task alongside the [`Application`](web_reference.html#aiohttp.web.Application "aiohttp.web.Application") can be done with a Cleanup Context function like:
    
    
    @contextlib.asynccontextmanager
    async def run_other_task(_app):
        task = asyncio.create_task(other_long_task())
    
        yield
    
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task  # Ensure any exceptions etc. are raised.
    
    app.cleanup_ctx.append(run_other_task)
    

Or a separate process can be run with something like:
    
    
    @contextlib.asynccontextmanager
    async def run_process(_app):
        proc = await asyncio.create_subprocess_exec(path)
    
        yield
    
        if proc.returncode is None:
            proc.terminate()
        await proc.wait()
    
    app.cleanup_ctx.append(run_process)
    

## Handling error pages¶

Pages like _404 Not Found_ and _500 Internal Error_ could be handled by custom middleware, see [polls demo](https://aiohttp-demos.readthedocs.io/en/latest/tutorial.html#aiohttp-demos-polls-middlewares "\(in aiohttp-demos v0.2\)") for example.

## Deploying behind a Proxy¶

As discussed in [Server Deployment](deployment.html#aiohttp-deployment) the preferable way is deploying _aiohttp_ web server behind a _Reverse Proxy Server_ like [nginx](glossary.html#term-nginx) for production usage.

In this way properties like [`BaseRequest.scheme`](web_reference.html#aiohttp.web.BaseRequest.scheme "aiohttp.web.BaseRequest.scheme") [`BaseRequest.host`](web_reference.html#aiohttp.web.BaseRequest.host "aiohttp.web.BaseRequest.host") and [`BaseRequest.remote`](web_reference.html#aiohttp.web.BaseRequest.remote "aiohttp.web.BaseRequest.remote") are incorrect.

Real values should be given from proxy server, usually either `Forwarded` or old-fashion `X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto` HTTP headers are used.

_aiohttp_ does not take _forwarded_ headers into account by default because it produces _security issue_ : HTTP client might add these headers too, pushing non-trusted data values.

That’s why _aiohttp server_ should setup _forwarded_ headers in custom middleware in tight conjunction with _reverse proxy configuration_.

For changing [`BaseRequest.scheme`](web_reference.html#aiohttp.web.BaseRequest.scheme "aiohttp.web.BaseRequest.scheme") [`BaseRequest.host`](web_reference.html#aiohttp.web.BaseRequest.host "aiohttp.web.BaseRequest.host") [`BaseRequest.remote`](web_reference.html#aiohttp.web.BaseRequest.remote "aiohttp.web.BaseRequest.remote") and [`BaseRequest.client_max_size`](web_reference.html#aiohttp.web.BaseRequest.client_max_size "aiohttp.web.BaseRequest.client_max_size") the middleware might use [`BaseRequest.clone()`](web_reference.html#aiohttp.web.BaseRequest.clone "aiohttp.web.BaseRequest.clone").

See also

<https://github.com/aio-libs/aiohttp-remotes> provides secure helpers for modifying _scheme_ , _host_ and _remote_ attributes according to `Forwarded` and `X-Forwarded-*` HTTP headers.

## CORS support¶

[`aiohttp.web`](web.html#module-aiohttp.web "aiohttp.web") itself does not support [Cross-Origin Resource Sharing](https://en.wikipedia.org/wiki/Cross-origin_resource_sharing), but there is an aiohttp plugin for it: [aiohttp-cors](https://github.com/aio-libs/aiohttp-cors).

## Debug Toolbar¶

[aiohttp-debugtoolbar](https://github.com/aio-libs/aiohttp_debugtoolbar) is a very useful library that provides a debugging toolbar while you’re developing an [`aiohttp.web`](web.html#module-aiohttp.web "aiohttp.web") application.

Install it with `pip`:
    
    
    $ pip install aiohttp_debugtoolbar
    

Just call `aiohttp_debugtoolbar.setup()`:
    
    
    import aiohttp_debugtoolbar
    from aiohttp_debugtoolbar import toolbar_middleware_factory
    
    app = web.Application()
    aiohttp_debugtoolbar.setup(app)
    

The toolbar is ready to use. Enjoy!!!

## Dev Tools¶

[aiohttp-devtools](https://github.com/aio-libs/aiohttp-devtools) provides a couple of tools to simplify development of [`aiohttp.web`](web.html#module-aiohttp.web "aiohttp.web") applications.

Install with `pip`:
    
    
    $ pip install aiohttp-devtools
    

`adev runserver` provides a development server with auto-reload, live-reload, static file serving.

Documentation and a complete tutorial of creating and running an app locally are available at [aiohttp-devtools](https://github.com/aio-libs/aiohttp-devtools).

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
    * Advanced Usage
    * [Low Level](web_lowlevel.html)
    * [Reference](web_reference.html)
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

(C)aiohttp contributors. | Powered by [Sphinx 9.0.4](http://sphinx-doc.org/) | [Page source](_sources/web_advanced.rst.txt)

[ ](https://github.com/aio-libs/aiohttp)
