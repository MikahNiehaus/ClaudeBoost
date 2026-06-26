"""Known source locations for common technologies.

Maps technology names to their official documentation GitHub repos
and documentation sites for the four-layer research waterfall.

Covers languages, frameworks, libraries, best practices, cloud services,
databases, testing, DevOps, and security across all major tech stacks.
"""

SOURCE_MAP = {
    # =====================================================================
    # Languages
    # =====================================================================
    "python": {
        "github": "python/cpython",
        "docs_path": "Doc",
        "extensions": ".rst",
        "doc_root": "https://docs.python.org/3",
    },
    "typescript": {
        "github": "microsoft/TypeScript-Website",
        "docs_path": "packages/documentation/copy/en",
        "doc_root": "https://www.typescriptlang.org/docs",
    },
    "javascript": {
        "doc_root": "https://developer.mozilla.org/en-US/docs/Web/JavaScript",
    },
    "csharp": {
        "github": "dotnet/docs",
        "docs_path": "docs/csharp",
        "doc_root": "https://learn.microsoft.com/en-us/dotnet/csharp",
    },
    "rust": {
        "github": "rust-lang/book",
        "docs_path": "src",
        "doc_root": "https://doc.rust-lang.org/book",
    },
    "go": {
        "github": "golang/website",
        "docs_path": "_content",
        "doc_root": "https://go.dev/doc",
    },
    "java": {
        "doc_root": "https://docs.oracle.com/en/java/javase/21/docs/api",
    },
    "kotlin": {
        "github": "JetBrains/kotlin-web-site",
        "docs_path": "docs/topics",
        "doc_root": "https://kotlinlang.org/docs",
    },
    "swift": {
        "github": "apple/swift-book",
        "docs_path": "TSPL.docc",
        "doc_root": "https://docs.swift.org/swift-book",
    },
    "php": {
        "doc_root": "https://www.php.net/manual/en",
    },
    "ruby": {
        "doc_root": "https://ruby-doc.org/core",
    },
    "dart": {
        "github": "dart-lang/site-www",
        "docs_path": "src/language",
        "doc_root": "https://dart.dev/language",
    },
    "lua": {
        "doc_root": "https://www.lua.org/manual/5.4",
    },
    "sql": {
        "doc_root": "https://www.w3schools.com/sql",
    },
    "html": {
        "doc_root": "https://developer.mozilla.org/en-US/docs/Web/HTML",
    },
    "css": {
        "doc_root": "https://developer.mozilla.org/en-US/docs/Web/CSS",
    },
    "powershell": {
        "github": "MicrosoftDocs/PowerShell-Docs",
        "docs_path": "reference/7.5",
        "doc_root": "https://learn.microsoft.com/en-us/powershell",
    },
    "bash": {
        "doc_root": "https://www.gnu.org/software/bash/manual",
    },

    # =====================================================================
    # .NET / C# Ecosystem
    # =====================================================================
    "dotnet": {
        "github": "dotnet/docs",
        "docs_path": "docs",
        "doc_root": "https://learn.microsoft.com/en-us/dotnet",
    },
    "aspnet": {
        "github": "dotnet/AspNetCore.Docs",
        "docs_path": "aspnetcore",
        "doc_root": "https://learn.microsoft.com/en-us/aspnet/core",
    },
    "aspnet-mvc": {
        "github": "dotnet/AspNetCore.Docs",
        "docs_path": "aspnetcore/mvc",
        "doc_root": "https://learn.microsoft.com/en-us/aspnet/core/mvc",
    },
    "razor-pages": {
        "github": "dotnet/AspNetCore.Docs",
        "docs_path": "aspnetcore/razor-pages",
        "doc_root": "https://learn.microsoft.com/en-us/aspnet/core/razor-pages",
    },
    "minimal-apis": {
        "github": "dotnet/AspNetCore.Docs",
        "docs_path": "aspnetcore/fundamentals/minimal-apis",
        "doc_root": "https://learn.microsoft.com/en-us/aspnet/core/fundamentals/minimal-apis",
    },
    "blazor": {
        "github": "dotnet/AspNetCore.Docs",
        "docs_path": "aspnetcore/blazor",
        "doc_root": "https://learn.microsoft.com/en-us/aspnet/core/blazor",
    },
    "efcore": {
        "github": "dotnet/EntityFramework.Docs",
        "docs_path": "entity-framework/core",
        "doc_root": "https://learn.microsoft.com/en-us/ef/core",
    },
    "signalr": {
        "github": "dotnet/AspNetCore.Docs",
        "docs_path": "aspnetcore/signalr",
        "doc_root": "https://learn.microsoft.com/en-us/aspnet/core/signalr",
    },
    "dotnet-identity": {
        "github": "dotnet/AspNetCore.Docs",
        "docs_path": "aspnetcore/security",
        "doc_root": "https://learn.microsoft.com/en-us/aspnet/core/security",
    },
    "maui": {
        "github": "dotnet/docs-maui",
        "docs_path": "docs",
        "doc_root": "https://learn.microsoft.com/en-us/dotnet/maui",
    },
    "xunit": {
        "github": "xunit/xunit",
        "docs_path": "docs",
        "doc_root": "https://xunit.net",
    },
    "nunit": {
        "github": "nunit/docs",
        "docs_path": "docs",
        "doc_root": "https://docs.nunit.org",
    },

    # =====================================================================
    # JavaScript / Frontend Frameworks
    # =====================================================================
    "react": {
        "github": "reactjs/react.dev",
        "docs_path": "src/content",
        "doc_root": "https://react.dev",
    },
    "react-native": {
        "github": "facebook/react-native-website",
        "docs_path": "docs",
        "doc_root": "https://reactnative.dev/docs",
    },
    "expo": {
        "github": "expo/expo",
        "docs_path": "docs/pages",
        "doc_root": "https://docs.expo.dev",
    },
    "nextjs": {
        "github": "vercel/next.js",
        "docs_path": "docs",
        "doc_root": "https://nextjs.org/docs",
    },
    "vue": {
        "github": "vuejs/docs",
        "docs_path": "src",
        "doc_root": "https://vuejs.org",
    },
    "angular": {
        "github": "angular/angular",
        "docs_path": "adev/src/content",
        "doc_root": "https://angular.dev",
    },
    "svelte": {
        "github": "sveltejs/svelte",
        "docs_path": "documentation/docs",
        "doc_root": "https://svelte.dev/docs",
    },
    "astro": {
        "github": "withastro/docs",
        "docs_path": "src/content/docs/en",
        "doc_root": "https://docs.astro.build",
    },
    "express": {
        "github": "expressjs/expressjs.com",
        "docs_path": "en",
        "doc_root": "https://expressjs.com",
    },
    "nestjs": {
        "github": "nestjs/docs.nestjs.com",
        "docs_path": "content",
        "doc_root": "https://docs.nestjs.com",
    },
    "nodejs": {
        "doc_root": "https://nodejs.org/en/docs",
    },
    "deno": {
        "github": "denoland/docs",
        "docs_path": "runtime",
        "doc_root": "https://docs.deno.com",
    },
    "htmx": {
        "github": "bigskysoftware/htmx",
        "docs_path": "www/content/docs",
        "doc_root": "https://htmx.org/docs",
    },
    "redux": {
        "github": "reduxjs/redux",
        "docs_path": "docs",
        "doc_root": "https://redux.js.org",
    },
    "react-query": {
        "github": "TanStack/query",
        "docs_path": "docs",
        "doc_root": "https://tanstack.com/query",
    },
    "react-router": {
        "github": "remix-run/react-router",
        "docs_path": "docs",
        "doc_root": "https://reactrouter.com",
    },
    "react-navigation": {
        "github": "react-navigation/react-navigation.github.io",
        "docs_path": "docs",
        "doc_root": "https://reactnavigation.org/docs",
    },
    "zustand": {
        "github": "pmndrs/zustand",
        "docs_path": "docs",
        "doc_root": "https://zustand-demo.pmnd.rs",
    },

    # =====================================================================
    # Python Frameworks
    # =====================================================================
    "django": {
        "github": "django/django",
        "docs_path": "docs",
        "extensions": ".txt,.rst",
        "doc_root": "https://docs.djangoproject.com",
    },
    "fastapi": {
        "github": "fastapi/fastapi",
        "docs_path": "docs/en/docs",
        "doc_root": "https://fastapi.tiangolo.com",
    },
    "flask": {
        "github": "pallets/flask",
        "docs_path": "docs",
        "extensions": ".rst",
        "doc_root": "https://flask.palletsprojects.com",
    },
    "sqlalchemy": {
        "doc_root": "https://docs.sqlalchemy.org",
    },
    "celery": {
        "github": "celery/celery",
        "docs_path": "docs",
        "extensions": ".rst",
        "doc_root": "https://docs.celeryq.dev",
    },
    "pydantic": {
        "github": "pydantic/pydantic",
        "docs_path": "docs",
        "doc_root": "https://docs.pydantic.dev",
    },

    # =====================================================================
    # Databases
    # =====================================================================
    "postgresql": {
        "github": "postgres/postgres",
        "docs_path": "doc/src/sgml",
        "extensions": ".sgml",
        "doc_root": "https://www.postgresql.org/docs/current",
    },
    "sqlserver": {
        "doc_root": "https://learn.microsoft.com/en-us/sql/sql-server",
    },
    "mongodb": {
        "github": "mongodb/docs",
        "docs_path": "source",
        "extensions": ".txt,.rst",
        "doc_root": "https://www.mongodb.com/docs",
    },
    "redis": {
        "github": "redis/redis-doc",
        "docs_path": "docs",
        "doc_root": "https://redis.io/docs",
    },
    "sqlite": {
        "doc_root": "https://www.sqlite.org/docs.html",
    },
    "prisma": {
        "github": "prisma/docs",
        "docs_path": "content",
        "doc_root": "https://www.prisma.io/docs",
    },
    "supabase": {
        "github": "supabase/supabase",
        "docs_path": "apps/docs/content",
        "doc_root": "https://supabase.com/docs",
    },
    "firebase": {
        "doc_root": "https://firebase.google.com/docs",
    },
    "elasticsearch": {
        "doc_root": "https://www.elastic.co/guide/en/elasticsearch/reference/current",
    },
    "chromadb": {
        "github": "chroma-core/docs",
        "docs_path": "docs",
        "doc_root": "https://docs.trychroma.com",
    },

    # =====================================================================
    # Cloud / Azure / AWS / GCP
    # =====================================================================
    "azure": {
        "doc_root": "https://learn.microsoft.com/en-us/azure",
    },
    "azure-functions": {
        "github": "MicrosoftDocs/azure-docs",
        "docs_path": "articles/azure-functions",
        "doc_root": "https://learn.microsoft.com/en-us/azure/azure-functions",
    },
    "azure-storage": {
        "doc_root": "https://learn.microsoft.com/en-us/azure/storage",
    },
    "azure-openai": {
        "doc_root": "https://learn.microsoft.com/en-us/azure/ai-services/openai",
    },
    "azure-devops": {
        "doc_root": "https://learn.microsoft.com/en-us/azure/devops",
    },
    "aws": {
        "doc_root": "https://docs.aws.amazon.com",
    },
    "gcp": {
        "doc_root": "https://cloud.google.com/docs",
    },
    "vercel": {
        "doc_root": "https://vercel.com/docs",
    },
    "cloudflare": {
        "github": "cloudflare/cloudflare-docs",
        "docs_path": "src/content/docs",
        "doc_root": "https://developers.cloudflare.com",
    },

    # =====================================================================
    # Infrastructure / DevOps
    # =====================================================================
    "docker": {
        "github": "docker/docs",
        "docs_path": "content",
        "doc_root": "https://docs.docker.com",
    },
    "kubernetes": {
        "github": "kubernetes/website",
        "docs_path": "content/en/docs",
        "doc_root": "https://kubernetes.io/docs",
    },
    "terraform": {
        "github": "hashicorp/terraform",
        "docs_path": "website/docs",
        "doc_root": "https://developer.hashicorp.com/terraform/docs",
    },
    "nginx": {
        "doc_root": "https://nginx.org/en/docs",
    },
    "github-actions": {
        "github": "github/docs",
        "docs_path": "content/actions",
        "doc_root": "https://docs.github.com/en/actions",
    },
    "git": {
        "github": "git/git",
        "docs_path": "Documentation",
        "extensions": ".txt",
        "doc_root": "https://git-scm.com/doc",
    },

    # =====================================================================
    # Testing
    # =====================================================================
    "playwright": {
        "github": "microsoft/playwright",
        "docs_path": "docs/src",
        "doc_root": "https://playwright.dev/docs",
    },
    "pytest": {
        "github": "pytest-dev/pytest",
        "docs_path": "doc/en",
        "extensions": ".rst",
        "doc_root": "https://docs.pytest.org",
    },
    "jest": {
        "github": "jestjs/jest",
        "docs_path": "website/docs",
        "doc_root": "https://jestjs.io/docs",
    },
    "vitest": {
        "github": "vitest-dev/vitest",
        "docs_path": "docs",
        "doc_root": "https://vitest.dev",
    },
    "cypress": {
        "github": "cypress-io/cypress-documentation",
        "docs_path": "docs",
        "doc_root": "https://docs.cypress.io",
    },
    "testing-library": {
        "github": "testing-library/testing-library-docs",
        "docs_path": "docs",
        "doc_root": "https://testing-library.com/docs",
    },
    "selenium": {
        "github": "SeleniumHQ/seleniumhq.github.io",
        "docs_path": "website_and_docs/content/documentation",
        "doc_root": "https://www.selenium.dev/documentation",
    },
    "storybook": {
        "github": "storybookjs/storybook",
        "docs_path": "docs",
        "doc_root": "https://storybook.js.org/docs",
    },

    # =====================================================================
    # Security
    # =====================================================================
    "owasp": {
        "github": "OWASP/CheatSheetSeries",
        "docs_path": "cheatsheets",
        "doc_root": "https://cheatsheetseries.owasp.org",
    },
    "jwt": {
        "doc_root": "https://jwt.io/introduction",
    },
    "oauth": {
        "doc_root": "https://oauth.net/2",
    },
    "auth0": {
        "doc_root": "https://auth0.com/docs",
    },

    # =====================================================================
    # UI / CSS / Design
    # =====================================================================
    "tailwindcss": {
        "github": "tailwindlabs/tailwindcss.com",
        "docs_path": "src/pages/docs",
        "doc_root": "https://tailwindcss.com/docs",
    },
    "bootstrap": {
        "github": "twbs/bootstrap",
        "docs_path": "site/content/docs/5.3",
        "doc_root": "https://getbootstrap.com/docs",
    },
    "sass": {
        "github": "sass/sass-site",
        "docs_path": "source/documentation",
        "doc_root": "https://sass-lang.com/documentation",
    },
    "accessibility": {
        "doc_root": "https://www.w3.org/WAI/WCAG22/quickref",
    },

    # =====================================================================
    # AI / ML
    # =====================================================================
    "langchain": {
        "github": "langchain-ai/langchain",
        "docs_path": "docs/docs",
        "doc_root": "https://python.langchain.com/docs",
    },
    "pytorch": {
        "github": "pytorch/pytorch",
        "docs_path": "docs/source",
        "extensions": ".rst",
        "doc_root": "https://pytorch.org/docs/stable",
    },
    "openai-api": {
        "doc_root": "https://platform.openai.com/docs",
    },
    "anthropic-api": {
        "doc_root": "https://docs.anthropic.com",
    },
    "huggingface": {
        "github": "huggingface/transformers",
        "docs_path": "docs/source/en",
        "doc_root": "https://huggingface.co/docs/transformers",
    },

    # =====================================================================
    # Build Tools / Package Managers
    # =====================================================================
    "vite": {
        "github": "vitejs/vite",
        "docs_path": "docs",
        "doc_root": "https://vite.dev",
    },
    "webpack": {
        "github": "webpack/webpack.js.org",
        "docs_path": "src/content",
        "doc_root": "https://webpack.js.org",
    },
    "eslint": {
        "github": "eslint/eslint",
        "docs_path": "docs/src/rules",
        "doc_root": "https://eslint.org/docs",
    },
    "prettier": {
        "github": "prettier/prettier",
        "docs_path": "docs",
        "doc_root": "https://prettier.io/docs",
    },
    "nuget": {
        "doc_root": "https://learn.microsoft.com/en-us/nuget",
    },

    # =====================================================================
    # API / Communication
    # =====================================================================
    "graphql": {
        "github": "graphql/graphql.github.io",
        "docs_path": "src/content/learn",
        "doc_root": "https://graphql.org/learn",
    },
    "rest-api": {
        "doc_root": "https://restfulapi.net",
    },
    "grpc": {
        "github": "grpc/grpc.io",
        "docs_path": "content/en/docs",
        "doc_root": "https://grpc.io/docs",
    },
    "websockets": {
        "doc_root": "https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API",
    },
    "openapi": {
        "doc_root": "https://swagger.io/docs/specification",
    },

    # =====================================================================
    # Message Queues / Event Systems
    # =====================================================================
    "rabbitmq": {
        "github": "rabbitmq/rabbitmq-website",
        "docs_path": "docs",
        "doc_root": "https://www.rabbitmq.com/docs",
    },

    # =====================================================================
    # Payments / Services (used in projects)
    # =====================================================================
    "stripe": {
        "doc_root": "https://docs.stripe.com",
    },
    "sendgrid": {
        "doc_root": "https://docs.sendgrid.com",
    },
    "google-maps": {
        "doc_root": "https://developers.google.com/maps/documentation",
    },

    # =====================================================================
    # Best Practices / Patterns / Architecture
    # =====================================================================
    "clean-architecture": {
        "doc_root": "https://learn.microsoft.com/en-us/dotnet/architecture/modern-web-apps-azure",
    },
    "design-patterns": {
        "github": "kamranahmedse/design-patterns-for-humans",
        "docs_path": ".",
        "doc_root": "https://refactoring.guru/design-patterns",
    },
    "solid-principles": {
        "doc_root": "https://www.digitalocean.com/community/conceptual-articles/s-o-l-i-d-the-first-five-principles-of-object-oriented-design",
    },
    "microservices": {
        "doc_root": "https://learn.microsoft.com/en-us/dotnet/architecture/microservices",
    },
    "web-performance": {
        "doc_root": "https://developer.mozilla.org/en-US/docs/Web/Performance",
    },
    "seo": {
        "doc_root": "https://developers.google.com/search/docs",
    },

    # =====================================================================
    # Mobile (from user projects)
    # =====================================================================
    "expo-router": {
        "doc_root": "https://docs.expo.dev/router/introduction",
    },
    "lottie": {
        "doc_root": "https://airbnb.io/lottie",
    },
    "i18next": {
        "github": "i18next/i18next",
        "docs_path": "docs",
        "doc_root": "https://www.i18next.com",
    },

    # =====================================================================
    # Other frameworks (from user projects)
    # =====================================================================
    "telerik": {
        "doc_root": "https://docs.telerik.com",
    },
    "kendo-react": {
        "doc_root": "https://www.telerik.com/kendo-react-ui/components",
    },
    "closedxml": {
        "github": "ClosedXML/ClosedXML",
        "docs_path": "docs",
        "doc_root": "https://closedxml.readthedocs.io",
    },
    "quartz-net": {
        "github": "quartznet/quartznet",
        "docs_path": "docs",
        "doc_root": "https://www.quartz-scheduler.net/documentation",
    },
    "odata": {
        "doc_root": "https://learn.microsoft.com/en-us/odata",
    },
    "dapr": {
        "github": "dapr/docs",
        "docs_path": "daprdocs/content/en",
        "doc_root": "https://docs.dapr.io",
    },

    # =====================================================================
    # Ruby / PHP
    # =====================================================================
    "rails": {
        "github": "rails/rails",
        "docs_path": "guides/source",
        "doc_root": "https://guides.rubyonrails.org",
    },
    "laravel": {
        "github": "laravel/docs",
        "docs_path": ".",
        "doc_root": "https://laravel.com/docs",
    },

    # =====================================================================
    # Java
    # =====================================================================
    "spring-boot": {
        "github": "spring-projects/spring-boot",
        "docs_path": "spring-boot-project/spring-boot-docs/src/docs",
        "doc_root": "https://docs.spring.io/spring-boot/docs/current/reference",
    },
}


# Topics to pre-seed during install (subset of SOURCE_MAP with GitHub repos).
# Each entry must have a working github repo + docs_path for Layer 1 clone.
SEED_TOPICS = [
    # === Languages ===
    {"topic": "python", "repo": "python/cpython", "path": "Doc", "extensions": ".rst"},
    {"topic": "typescript", "repo": "microsoft/TypeScript-Website", "path": "packages/documentation/copy/en"},
    {"topic": "csharp", "repo": "dotnet/docs", "path": "docs/csharp"},
    {"topic": "rust", "repo": "rust-lang/book", "path": "src"},
    {"topic": "go", "repo": "golang/website", "path": "_content"},
    {"topic": "kotlin", "repo": "JetBrains/kotlin-web-site", "path": "docs/topics"},
    {"topic": "swift", "repo": "apple/swift-book", "path": "TSPL.docc"},
    {"topic": "dart", "repo": "dart-lang/site-www", "path": "src/language"},
    {"topic": "powershell", "repo": "MicrosoftDocs/PowerShell-Docs", "path": "reference/7.5"},

    # === .NET / C# Ecosystem ===
    {"topic": "dotnet", "repo": "dotnet/docs", "path": "docs"},
    {"topic": "aspnet", "repo": "dotnet/AspNetCore.Docs", "path": "aspnetcore"},
    {"topic": "efcore", "repo": "dotnet/EntityFramework.Docs", "path": "entity-framework/core"},
    {"topic": "blazor", "repo": "dotnet/AspNetCore.Docs", "path": "aspnetcore/blazor"},
    {"topic": "signalr", "repo": "dotnet/AspNetCore.Docs", "path": "aspnetcore/signalr"},
    {"topic": "maui", "repo": "dotnet/docs-maui", "path": "docs"},
    {"topic": "xunit", "repo": "xunit/xunit", "path": "docs"},
    {"topic": "nunit", "repo": "nunit/docs", "path": "docs"},

    # === JavaScript / Frontend ===
    {"topic": "react", "repo": "reactjs/react.dev", "path": "src/content"},
    {"topic": "react-native", "repo": "facebook/react-native-website", "path": "docs"},
    {"topic": "expo", "repo": "expo/expo", "path": "docs/pages"},
    {"topic": "nextjs", "repo": "vercel/next.js", "path": "docs"},
    {"topic": "vue", "repo": "vuejs/docs", "path": "src"},
    {"topic": "angular", "repo": "angular/angular", "path": "adev/src/content"},
    {"topic": "svelte", "repo": "sveltejs/svelte", "path": "documentation/docs"},
    {"topic": "astro", "repo": "withastro/docs", "path": "src/content/docs/en"},
    {"topic": "express", "repo": "expressjs/expressjs.com", "path": "en"},
    {"topic": "nestjs", "repo": "nestjs/docs.nestjs.com", "path": "content"},
    {"topic": "deno", "repo": "denoland/docs", "path": "runtime"},
    {"topic": "htmx", "repo": "bigskysoftware/htmx", "path": "www/content/docs"},
    {"topic": "redux", "repo": "reduxjs/redux", "path": "docs"},
    {"topic": "react-query", "repo": "TanStack/query", "path": "docs"},
    {"topic": "react-router", "repo": "remix-run/react-router", "path": "docs"},
    {"topic": "react-navigation", "repo": "react-navigation/react-navigation.github.io", "path": "docs"},

    # === Python Frameworks ===
    {"topic": "django", "repo": "django/django", "path": "docs", "extensions": ".txt,.rst"},
    {"topic": "fastapi", "repo": "fastapi/fastapi", "path": "docs/en/docs"},
    {"topic": "flask", "repo": "pallets/flask", "path": "docs", "extensions": ".rst"},
    {"topic": "pydantic", "repo": "pydantic/pydantic", "path": "docs"},

    # === Databases ===
    {"topic": "postgresql", "repo": "postgres/postgres", "path": "doc/src/sgml", "extensions": ".sgml"},
    {"topic": "mongodb", "repo": "mongodb/docs", "path": "source", "extensions": ".txt,.rst"},
    {"topic": "redis", "repo": "redis/redis-doc", "path": "docs"},
    {"topic": "prisma", "repo": "prisma/docs", "path": "content"},
    {"topic": "chromadb", "repo": "chroma-core/docs", "path": "docs"},

    # === Cloud / Azure ===
    {"topic": "azure-functions", "repo": "MicrosoftDocs/azure-docs", "path": "articles/azure-functions"},
    {"topic": "cloudflare", "repo": "cloudflare/cloudflare-docs", "path": "src/content/docs"},

    # === Infrastructure / DevOps ===
    {"topic": "docker", "repo": "docker/docs", "path": "content"},
    {"topic": "kubernetes", "repo": "kubernetes/website", "path": "content/en/docs"},
    {"topic": "terraform", "repo": "hashicorp/terraform", "path": "website/docs"},
    {"topic": "github-actions", "repo": "github/docs", "path": "content/actions"},
    {"topic": "git", "repo": "git/git", "path": "Documentation", "extensions": ".txt"},

    # === Testing ===
    {"topic": "playwright", "repo": "microsoft/playwright", "path": "docs/src"},
    {"topic": "pytest", "repo": "pytest-dev/pytest", "path": "doc/en", "extensions": ".rst"},
    {"topic": "jest", "repo": "jestjs/jest", "path": "website/docs"},
    {"topic": "vitest", "repo": "vitest-dev/vitest", "path": "docs"},
    {"topic": "cypress", "repo": "cypress-io/cypress-documentation", "path": "docs"},
    {"topic": "testing-library", "repo": "testing-library/testing-library-docs", "path": "docs"},
    {"topic": "selenium", "repo": "SeleniumHQ/seleniumhq.github.io", "path": "website_and_docs/content/documentation"},
    {"topic": "storybook", "repo": "storybookjs/storybook", "path": "docs"},

    # === Security ===
    {"topic": "owasp", "repo": "OWASP/CheatSheetSeries", "path": "cheatsheets"},

    # === UI / CSS ===
    {"topic": "tailwindcss", "repo": "tailwindlabs/tailwindcss.com", "path": "src/pages/docs"},
    {"topic": "bootstrap", "repo": "twbs/bootstrap", "path": "site/content/docs/5.3"},
    {"topic": "sass", "repo": "sass/sass-site", "path": "source/documentation"},

    # === AI / ML ===
    {"topic": "langchain", "repo": "langchain-ai/langchain", "path": "docs/docs"},
    {"topic": "huggingface", "repo": "huggingface/transformers", "path": "docs/source/en"},

    # === Build Tools ===
    {"topic": "vite", "repo": "vitejs/vite", "path": "docs"},
    {"topic": "eslint", "repo": "eslint/eslint", "path": "docs/src/rules"},

    # === API / Communication ===
    {"topic": "graphql", "repo": "graphql/graphql.github.io", "path": "src/content/learn"},
    {"topic": "grpc", "repo": "grpc/grpc.io", "path": "content/en/docs"},

    # === Best Practices ===
    {"topic": "design-patterns", "repo": "kamranahmedse/design-patterns-for-humans", "path": "."},

    # === Other frameworks (from user projects) ===
    {"topic": "dapr", "repo": "dapr/docs", "path": "daprdocs/content/en"},
    {"topic": "i18next", "repo": "i18next/i18next", "path": "docs"},

    # === Ruby / PHP / Java ===
    {"topic": "rails", "repo": "rails/rails", "path": "guides/source"},
    {"topic": "laravel", "repo": "laravel/docs", "path": "."},
    {"topic": "spring-boot", "repo": "spring-projects/spring-boot", "path": "spring-boot-project/spring-boot-docs/src/docs"},
]
