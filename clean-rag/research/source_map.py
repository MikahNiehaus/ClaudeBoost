"""Known source locations for common technologies.

Maps technology names to their official documentation GitHub repos
and documentation sites for the four-layer research waterfall.

Covers languages, frameworks, libraries, best practices, cloud services,
databases, testing, DevOps, and security across all major tech stacks.
"""

# Category tree: maps each topic to its parent category folder.
# knowledge/ and databases/ mirror this structure:
#   knowledge/<category>/<topic>/...docs...
#   databases/<category>/<topic>/chroma/
TOPIC_CATEGORIES = {
    # Languages
    "python": "languages", "typescript": "languages", "javascript": "languages",
    "csharp": "languages", "rust": "languages", "go": "languages",
    "java": "languages", "kotlin": "languages", "swift": "languages",
    "php": "languages", "ruby": "languages", "dart": "languages",
    "lua": "languages", "sql": "languages", "html": "languages",
    "css": "languages", "powershell": "languages", "bash": "languages",

    # .NET / C# Ecosystem
    "dotnet": "dotnet", "aspnet": "dotnet", "aspnet-mvc": "dotnet",
    "razor-pages": "dotnet", "minimal-apis": "dotnet", "blazor": "dotnet",
    "efcore": "dotnet", "signalr": "dotnet", "dotnet-identity": "dotnet",
    "maui": "dotnet", "xunit": "dotnet", "nunit": "dotnet",

    # Frontend / JavaScript Frameworks
    "react": "frontend", "react-native": "frontend", "expo": "frontend",
    "nextjs": "frontend", "vue": "frontend", "angular": "frontend",
    "svelte": "frontend", "astro": "frontend", "deno": "frontend",
    "htmx": "frontend", "redux": "frontend", "react-query": "frontend",
    "react-router": "frontend", "react-navigation": "frontend",
    "zustand": "frontend",

    # Node.js Server Frameworks
    "express": "node-frameworks", "nestjs": "node-frameworks",
    "fastify": "node-frameworks", "nodejs": "node-frameworks",

    # Python Frameworks
    "django": "python-frameworks", "fastapi": "python-frameworks",
    "flask": "python-frameworks", "sqlalchemy": "python-frameworks",
    "celery": "python-frameworks", "pydantic": "python-frameworks",

    # Databases
    "postgresql": "databases", "sqlserver": "databases", "mongodb": "databases",
    "redis": "databases", "sqlite": "databases", "prisma": "databases",
    "supabase": "databases", "firebase": "databases",
    "elasticsearch": "databases", "chromadb": "databases",

    # Cloud / Azure / AWS / GCP
    "azure": "cloud", "azure-functions": "cloud", "azure-storage": "cloud",
    "azure-openai": "cloud", "azure-devops": "cloud", "aws": "cloud",
    "gcp": "cloud", "vercel": "cloud", "cloudflare": "cloud",

    # Infrastructure / DevOps
    "docker": "infrastructure", "kubernetes": "infrastructure",
    "terraform": "infrastructure", "nginx": "infrastructure",
    "github-actions": "infrastructure", "git": "infrastructure",

    # Testing
    "playwright": "testing", "pytest": "testing", "jest": "testing",
    "vitest": "testing", "cypress": "testing", "testing-library": "testing",
    "selenium": "testing", "storybook": "testing",

    # Security
    "owasp": "security", "jwt": "security", "oauth": "security",
    "auth0": "security",

    # UI / CSS / Design
    "tailwindcss": "ui", "bootstrap": "ui", "sass": "ui",
    "accessibility": "ui",

    # AI / ML
    "langchain": "ai", "pytorch": "ai", "openai-api": "ai",
    "anthropic-api": "ai", "huggingface": "ai",

    # Build Tools / Package Managers
    "vite": "tools", "webpack": "tools", "eslint": "tools",
    "prettier": "tools", "nuget": "tools",

    # API / Communication
    "graphql": "api", "rest-api": "api", "grpc": "api",
    "websockets": "api", "openapi": "api",

    # Message Queues
    "rabbitmq": "messaging",

    # Best Practices / Patterns
    "clean-architecture": "patterns", "design-patterns": "patterns",
    "solid-principles": "patterns", "microservices": "patterns",
    "web-performance": "patterns", "seo": "patterns",

    # Mobile
    "expo-router": "mobile", "lottie": "mobile", "i18next": "mobile",

    # Payments / Services
    "stripe": "services", "sendgrid": "services", "google-maps": "services",

    # Ruby Frameworks
    "rails": "ruby-frameworks", "sinatra": "ruby-frameworks",

    # PHP Frameworks
    "laravel": "php-frameworks", "symfony": "php-frameworks",

    # Java Frameworks
    "spring-boot": "java-frameworks",

    # .NET Libraries (not core framework)
    "telerik": "dotnet", "kendo-react": "dotnet", "closedxml": "dotnet",
    "quartz-net": "dotnet", "odata": "dotnet", "dapr": "dotnet",
}


def get_category(topic: str) -> str:
    """Get the category for a topic. Returns 'uncategorized' if not found."""
    return TOPIC_CATEGORIES.get(topic, "uncategorized")


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
# Category field matches TOPIC_CATEGORIES and determines the tree location.
SEED_TOPICS = [
    # === languages/ ===
    {"topic": "python", "category": "languages", "repo": "python/cpython", "path": "Doc", "extensions": ".rst"},
    {"topic": "typescript", "category": "languages", "repo": "microsoft/TypeScript-Website", "path": "packages/documentation/copy/en", "branch": "v2"},
    {"topic": "csharp", "category": "languages", "repo": "dotnet/docs", "path": "docs/csharp"},
    {"topic": "rust", "category": "languages", "repo": "rust-lang/book", "path": "src"},
    {"topic": "go", "category": "languages", "repo": "golang/website", "path": "_content"},
    {"topic": "kotlin", "category": "languages", "repo": "JetBrains/kotlin-web-site", "path": "docs/topics"},
    {"topic": "swift", "category": "languages", "repo": "apple/swift-book", "path": "TSPL.docc"},
    {"topic": "dart", "category": "languages", "repo": "dart-lang/site-www", "path": "src/language"},
    {"topic": "powershell", "category": "languages", "repo": "MicrosoftDocs/PowerShell-Docs", "path": "reference/7.5"},

    # === dotnet/ ===
    {"topic": "dotnet", "category": "dotnet", "repo": "dotnet/docs", "path": "docs"},
    {"topic": "aspnet", "category": "dotnet", "repo": "dotnet/AspNetCore.Docs", "path": "aspnetcore"},
    {"topic": "efcore", "category": "dotnet", "repo": "dotnet/EntityFramework.Docs", "path": "entity-framework/core"},
    {"topic": "blazor", "category": "dotnet", "repo": "dotnet/AspNetCore.Docs", "path": "aspnetcore/blazor"},
    {"topic": "signalr", "category": "dotnet", "repo": "dotnet/AspNetCore.Docs", "path": "aspnetcore/signalr"},
    {"topic": "maui", "category": "dotnet", "repo": "dotnet/docs-maui", "path": "docs"},
    {"topic": "xunit", "category": "dotnet", "repo": "xunit/xunit", "path": "docs"},
    {"topic": "nunit", "category": "dotnet", "repo": "nunit/docs", "path": "docs"},

    # === frontend/ ===
    {"topic": "react", "category": "frontend", "repo": "reactjs/react.dev", "path": "src/content"},
    {"topic": "react-native", "category": "frontend", "repo": "facebook/react-native-website", "path": "docs"},
    {"topic": "expo", "category": "frontend", "repo": "expo/expo", "path": "docs/pages"},
    {"topic": "nextjs", "category": "frontend", "repo": "vercel/next.js", "path": "docs", "branch": "canary"},
    {"topic": "vue", "category": "frontend", "repo": "vuejs/docs", "path": "src"},
    {"topic": "angular", "category": "frontend", "repo": "angular/angular", "path": "adev/src/content"},
    {"topic": "svelte", "category": "frontend", "repo": "sveltejs/svelte", "path": "documentation/docs"},
    {"topic": "astro", "category": "frontend", "repo": "withastro/docs", "path": "src/content/docs/en"},
    {"topic": "express", "category": "frontend", "repo": "expressjs/expressjs.com", "path": "en"},
    {"topic": "nestjs", "category": "frontend", "repo": "nestjs/docs.nestjs.com", "path": "content"},
    {"topic": "deno", "category": "frontend", "repo": "denoland/docs", "path": "runtime"},
    {"topic": "htmx", "category": "frontend", "repo": "bigskysoftware/htmx", "path": "www/content/docs"},
    {"topic": "redux", "category": "frontend", "repo": "reduxjs/redux", "path": "docs"},
    {"topic": "react-query", "category": "frontend", "repo": "TanStack/query", "path": "docs"},
    {"topic": "react-router", "category": "frontend", "repo": "remix-run/react-router", "path": "docs"},
    {"topic": "react-navigation", "category": "frontend", "repo": "react-navigation/react-navigation.github.io", "path": "docs"},

    # === python-frameworks/ ===
    {"topic": "django", "category": "python-frameworks", "repo": "django/django", "path": "docs", "extensions": ".txt,.rst"},
    {"topic": "fastapi", "category": "python-frameworks", "repo": "fastapi/fastapi", "path": "docs/en/docs"},
    {"topic": "flask", "category": "python-frameworks", "repo": "pallets/flask", "path": "docs", "extensions": ".rst"},
    {"topic": "pydantic", "category": "python-frameworks", "repo": "pydantic/pydantic", "path": "docs"},

    # === databases/ ===
    {"topic": "postgresql", "category": "databases", "repo": "postgres/postgres", "path": "doc/src/sgml", "extensions": ".sgml"},
    {"topic": "mongodb", "category": "databases", "repo": "mongodb/docs", "path": "source", "extensions": ".txt,.rst"},
    {"topic": "redis", "category": "databases", "repo": "redis/redis-doc", "path": "docs"},
    {"topic": "prisma", "category": "databases", "repo": "prisma/docs", "path": "content"},
    {"topic": "chromadb", "category": "databases", "repo": "chroma-core/docs", "path": "docs"},

    # === cloud/ ===
    {"topic": "azure-functions", "category": "cloud", "repo": "MicrosoftDocs/azure-docs", "path": "articles/azure-functions"},
    {"topic": "cloudflare", "category": "cloud", "repo": "cloudflare/cloudflare-docs", "path": "src/content/docs"},

    # === infrastructure/ ===
    {"topic": "docker", "category": "infrastructure", "repo": "docker/docs", "path": "content"},
    {"topic": "kubernetes", "category": "infrastructure", "repo": "kubernetes/website", "path": "content/en/docs"},
    {"topic": "terraform", "category": "infrastructure", "repo": "hashicorp/terraform", "path": "website/docs"},
    {"topic": "github-actions", "category": "infrastructure", "repo": "github/docs", "path": "content/actions"},
    {"topic": "git", "category": "infrastructure", "repo": "git/git", "path": "Documentation", "extensions": ".txt"},

    # === testing/ ===
    {"topic": "playwright", "category": "testing", "repo": "microsoft/playwright", "path": "docs/src"},
    {"topic": "pytest", "category": "testing", "repo": "pytest-dev/pytest", "path": "doc/en", "extensions": ".rst"},
    {"topic": "jest", "category": "testing", "repo": "jestjs/jest", "path": "website/docs"},
    {"topic": "vitest", "category": "testing", "repo": "vitest-dev/vitest", "path": "docs"},
    {"topic": "cypress", "category": "testing", "repo": "cypress-io/cypress-documentation", "path": "docs"},
    {"topic": "testing-library", "category": "testing", "repo": "testing-library/testing-library-docs", "path": "docs"},
    {"topic": "selenium", "category": "testing", "repo": "SeleniumHQ/seleniumhq.github.io", "path": "website_and_docs/content/documentation"},
    {"topic": "storybook", "category": "testing", "repo": "storybookjs/storybook", "path": "docs"},

    # === security/ ===
    {"topic": "owasp", "category": "security", "repo": "OWASP/CheatSheetSeries", "path": "cheatsheets"},

    # === ui/ ===
    {"topic": "tailwindcss", "category": "ui", "repo": "tailwindlabs/tailwindcss.com", "path": "src/pages/docs"},
    {"topic": "bootstrap", "category": "ui", "repo": "twbs/bootstrap", "path": "site/content/docs/5.3"},
    {"topic": "sass", "category": "ui", "repo": "sass/sass-site", "path": "source/documentation"},

    # === ai/ ===
    {"topic": "langchain", "category": "ai", "repo": "langchain-ai/langchain", "path": "docs"},
    {"topic": "huggingface", "category": "ai", "repo": "huggingface/transformers", "path": "docs/source/en"},

    # === tools/ ===
    {"topic": "vite", "category": "tools", "repo": "vitejs/vite", "path": "docs"},
    {"topic": "eslint", "category": "tools", "repo": "eslint/eslint", "path": "docs/src/rules"},

    # === api/ ===
    {"topic": "graphql", "category": "api", "repo": "graphql/graphql-spec", "path": "spec"},
    {"topic": "grpc", "category": "api", "repo": "grpc/grpc.io", "path": "content/en/docs"},

    # === patterns/ ===
    {"topic": "design-patterns", "category": "patterns", "repo": "kamranahmedse/design-patterns-for-humans", "path": ".", "extensions": ".md"},

    # === other/ ===
    {"topic": "dapr", "category": "other", "repo": "dapr/docs", "path": "daprdocs/content/en"},
    {"topic": "i18next", "category": "other", "repo": "i18next/i18next", "path": "docs"},
    {"topic": "rails", "category": "other", "repo": "rails/rails", "path": "guides/source"},
    {"topic": "laravel", "category": "other", "repo": "laravel/docs", "path": "."},
    {"topic": "spring-boot", "category": "other", "repo": "spring-projects/spring-boot", "path": "spring-boot-project/spring-boot-docs/src/docs"},
]
