<!-- Source: https://publicapis.io/blog/api-security-best-practices | Tier: B | Topic: aiohttp-security | Fetched: 2026-06-26 -->

[Public APIs](/)

[📚 APIs](/apis)[Blog](/blog)[Bookmarks](/collections)[💎 Sponsor](/sponsors)[💡 List Your API](/submit)

### Categories

  * [Development](/category/development)
  * [Data Access](/category/data-access)
  * [Finance](/category/finance)
  * [Cryptocurrency](/category/cryptocurrency)
  * [Games & Comics](/category/games-and-comics)
  * [Geocoding](/category/geocoding)
  * [Open Data](/category/open-data)
  * [Transportation](/category/transportation)
  * [Music](/category/music)
  * [Media](/category/media)
  * [Social](/category/social)
  * [Sports & Fitness](/category/sports-and-fitness)
  * [Weather](/category/weather)
  * [Shopping](/category/shopping)
  * [Food & Drink](/category/food-and-drink)
  * [Health](/category/health)
  * [Calendar](/category/calendar)
  * [Government](/category/government)
  * [Video](/category/video)
  * [Science](/category/science)
  * [Jobs](/category/jobs)
  * [Animals](/category/animals)
  * [Machine Learning](/category/machine-learning)
  * [Documents & Productivity](/category/documents-and-productivity)
  * [Cloud Storage & File Sharing](/category/cloud-storage-and-file-sharing)
  * [Security](/category/security)
  * [Analytics](/category/analytics)
  * [Anime](/category/anime)
  * [Dictionaries](/category/dictionaries)
  * [News](/category/news)
  * [URL Shorteners](/category/url-shorteners)
  * [Art & Design](/category/art-and-design)
  * [IoT](/category/iot)
  * [Environment](/category/environment)
  * [Business](/category/business)
  * [Books](/category/books)
  * [Vehicle](/category/vehicle)
  * [Personality](/category/personality)
  * [Text Analysis](/category/text-analysis)
  * [Currency Exchange](/category/currency-exchange)
  * [Photography](/category/photography)
  * [Utilities](/category/utilities)



TOTAL RESOURCES: **0**

[Browse 1000+ Public APIs](/)  


# API Security Best Practices: The Complete Guide for 2026

5 months ago

API security is critical in 2026. With APIs handling sensitive data and business logic, a single vulnerability can expose your entire system. This guide covers essential security best practices every developer should implement.

## API Security Checklist

Category | Practice | Priority  
---|---|---  
Authentication | Use OAuth 2.0 or API keys | Critical  
Authorization | Implement RBAC | Critical  
Transport | HTTPS only | Critical  
Input | Validate all inputs | Critical  
Rate Limiting | Prevent abuse | High  
Logging | Audit all requests | High  
Error Handling | Don't leak info | High  
CORS | Restrict origins | Medium  
  
* * *

## 1\. Authentication Best Practices

### API Keys

Simple but effective for server-to-server communication:
    
    
    // Express middleware for API key validation
    function validateApiKey(req, res, next) {
      const apiKey = req.headers['x-api-key'] || req.query.api_key;
    
      if (!apiKey) {
        return res.status(401).json({
          error: 'API key required',
          code: 'MISSING_API_KEY'
        });
      }
    
      // Use constant-time comparison to prevent timing attacks
      const validKey = process.env.API_KEY;
      const isValid = crypto.timingSafeEqual(
        Buffer.from(apiKey),
        Buffer.from(validKey)
      );
    
      if (!isValid) {
        return res.status(401).json({
          error: 'Invalid API key',
          code: 'INVALID_API_KEY'
        });
      }
    
      next();
    }
    
    app.use('/api', validateApiKey);
    

### JWT Authentication

For user-based authentication:
    
    
    const jwt = require('jsonwebtoken');
    
    const JWT_SECRET = process.env.JWT_SECRET;
    const JWT_EXPIRY = '15m'; // Short-lived tokens
    const REFRESH_EXPIRY = '7d';
    
    function generateTokens(userId, role) {
      const accessToken = jwt.sign(
        { userId, role, type: 'access' },
        JWT_SECRET,
        { expiresIn: JWT_EXPIRY }
      );
    
      const refreshToken = jwt.sign(
        { userId, type: 'refresh' },
        JWT_SECRET,
        { expiresIn: REFRESH_EXPIRY }
      );
    
      return { accessToken, refreshToken };
    }
    
    function verifyToken(req, res, next) {
      const authHeader = req.headers.authorization;
    
      if (!authHeader?.startsWith('Bearer ')) {
        return res.status(401).json({ error: 'No token provided' });
      }
    
      const token = authHeader.split(' ')[1];
    
      try {
        const decoded = jwt.verify(token, JWT_SECRET);
    
        if (decoded.type !== 'access') {
          return res.status(401).json({ error: 'Invalid token type' });
        }
    
        req.user = decoded;
        next();
      } catch (error) {
        if (error.name === 'TokenExpiredError') {
          return res.status(401).json({ error: 'Token expired', code: 'TOKEN_EXPIRED' });
        }
        return res.status(401).json({ error: 'Invalid token' });
      }
    }
    

### OAuth 2.0 Implementation

For third-party integrations:
    
    
    const passport = require('passport');
    const OAuth2Strategy = require('passport-oauth2');
    
    passport.use('oauth2', new OAuth2Strategy({
        authorizationURL: 'https://provider.com/oauth/authorize',
        tokenURL: 'https://provider.com/oauth/token',
        clientID: process.env.OAUTH_CLIENT_ID,
        clientSecret: process.env.OAUTH_CLIENT_SECRET,
        callbackURL: 'https://yourapi.com/auth/callback',
        scope: ['read', 'write'],
        state: true // CSRF protection
      },
      async (accessToken, refreshToken, profile, done) => {
        // Store tokens securely
        const user = await User.findOrCreate({
          providerId: profile.id,
          accessToken: encrypt(accessToken),
          refreshToken: encrypt(refreshToken)
        });
        return done(null, user);
      }
    ));
    

* * *

## 2\. Authorization (RBAC)

Implement Role-Based Access Control:
    
    
    // Define permissions
    const permissions = {
      admin: ['read', 'write', 'delete', 'manage_users'],
      editor: ['read', 'write'],
      viewer: ['read']
    };
    
    // Authorization middleware
    function authorize(...requiredPermissions) {
      return (req, res, next) => {
        const userRole = req.user?.role;
    
        if (!userRole) {
          return res.status(401).json({ error: 'Authentication required' });
        }
    
        const userPermissions = permissions[userRole] || [];
        const hasPermission = requiredPermissions.every(
          perm => userPermissions.includes(perm)
        );
    
        if (!hasPermission) {
          return res.status(403).json({
            error: 'Insufficient permissions',
            required: requiredPermissions,
            userRole
          });
        }
    
        next();
      };
    }
    
    // Usage
    app.get('/api/users', verifyToken, authorize('read'), getUsers);
    app.post('/api/users', verifyToken, authorize('write', 'manage_users'), createUser);
    app.delete('/api/users/:id', verifyToken, authorize('delete', 'manage_users'), deleteUser);
    

### Resource-Level Authorization

Check ownership before allowing access:
    
    
    async function authorizeResource(req, res, next) {
      const { id } = req.params;
      const userId = req.user.userId;
    
      const resource = await Resource.findById(id);
    
      if (!resource) {
        return res.status(404).json({ error: 'Resource not found' });
      }
    
      // Check if user owns the resource or is admin
      if (resource.ownerId !== userId && req.user.role !== 'admin') {
        return res.status(403).json({ error: 'Access denied' });
      }
    
      req.resource = resource;
      next();
    }
    
    app.put('/api/posts/:id', verifyToken, authorizeResource, updatePost);
    

* * *

## 3\. Input Validation

Never trust client input. Validate everything:
    
    
    const Joi = require('joi');
    
    // Define validation schemas
    const schemas = {
      createUser: Joi.object({
        email: Joi.string().email().required(),
        password: Joi.string().min(8).max(128).required(),
        name: Joi.string().min(1).max(100).required(),
        role: Joi.string().valid('viewer', 'editor').default('viewer')
      }),
    
      updateUser: Joi.object({
        email: Joi.string().email(),
        name: Joi.string().min(1).max(100)
      }).min(1) // At least one field required
    };
    
    // Validation middleware
    function validate(schemaName) {
      return (req, res, next) => {
        const schema = schemas[schemaName];
    
        if (!schema) {
          return res.status(500).json({ error: 'Validation schema not found' });
        }
    
        const { error, value } = schema.validate(req.body, {
          abortEarly: false,
          stripUnknown: true // Remove unknown fields
        });
    
        if (error) {
          return res.status(400).json({
            error: 'Validation failed',
            details: error.details.map(d => ({
              field: d.path.join('.'),
              message: d.message
            }))
          });
        }
    
        req.body = value; // Use sanitized data
        next();
      };
    }
    
    app.post('/api/users', validate('createUser'), createUser);
    

### Prevent SQL Injection

Always use parameterized queries:
    
    
    // BAD - SQL Injection vulnerable
    const query = `SELECT * FROM users WHERE id = ${req.params.id}`;
    
    // GOOD - Parameterized query
    const query = 'SELECT * FROM users WHERE id = $1';
    const result = await db.query(query, [req.params.id]);
    
    // With an ORM (Prisma)
    const user = await prisma.user.findUnique({
      where: { id: parseInt(req.params.id) }
    });
    

### Prevent NoSQL Injection
    
    
    // BAD - NoSQL Injection vulnerable
    const user = await User.findOne({ username: req.body.username });
    
    // GOOD - Validate and sanitize
    const username = String(req.body.username).slice(0, 50);
    const user = await User.findOne({ username });
    
    // Or use mongo-sanitize
    const sanitize = require('mongo-sanitize');
    const user = await User.findOne({ username: sanitize(req.body.username) });
    

* * *

## 4\. Rate Limiting

Protect against abuse and DDoS:
    
    
    const rateLimit = require('express-rate-limit');
    const RedisStore = require('rate-limit-redis');
    
    // General rate limiter
    const generalLimiter = rateLimit({
      windowMs: 15 * 60 * 1000, // 15 minutes
      max: 100, // 100 requests per window
      standardHeaders: true,
      legacyHeaders: false,
      message: {
        error: 'Too many requests',
        retryAfter: '15 minutes'
      }
    });
    
    // Strict limiter for auth endpoints
    const authLimiter = rateLimit({
      windowMs: 60 * 60 * 1000, // 1 hour
      max: 5, // 5 attempts per hour
      skipSuccessfulRequests: true, // Only count failures
      message: {
        error: 'Too many login attempts',
        retryAfter: '1 hour'
      }
    });
    
    // API key-based rate limiting
    const apiKeyLimiter = rateLimit({
      windowMs: 60 * 1000, // 1 minute
      max: 60, // 60 requests per minute
      keyGenerator: (req) => req.headers['x-api-key'] || req.ip,
      store: new RedisStore({
        sendCommand: (...args) => redisClient.call(...args)
      })
    });
    
    app.use('/api', generalLimiter);
    app.use('/api/auth', authLimiter);
    app.use('/api/v1', apiKeyLimiter);
    

### Sliding Window Rate Limiter

More precise rate limiting:
    
    
    const Redis = require('ioredis');
    const redis = new Redis();
    
    async function slidingWindowRateLimit(key, limit, windowSeconds) {
      const now = Date.now();
      const windowStart = now - (windowSeconds * 1000);
    
      const multi = redis.multi();
    
      // Remove old entries
      multi.zremrangebyscore(key, 0, windowStart);
    
      // Add current request
      multi.zadd(key, now, `${now}-${Math.random()}`);
    
      // Count requests in window
      multi.zcard(key);
    
      // Set expiry
      multi.expire(key, windowSeconds);
    
      const results = await multi.exec();
      const requestCount = results[2][1];
    
      return {
        allowed: requestCount <= limit,
        remaining: Math.max(0, limit - requestCount),
        resetAt: new Date(now + windowSeconds * 1000)
      };
    }
    
    // Middleware
    async function rateLimitMiddleware(req, res, next) {
      const key = `ratelimit:${req.headers['x-api-key'] || req.ip}`;
      const { allowed, remaining, resetAt } = await slidingWindowRateLimit(key, 100, 60);
    
      res.setHeader('X-RateLimit-Limit', 100);
      res.setHeader('X-RateLimit-Remaining', remaining);
      res.setHeader('X-RateLimit-Reset', resetAt.toISOString());
    
      if (!allowed) {
        return res.status(429).json({
          error: 'Rate limit exceeded',
          retryAfter: resetAt.toISOString()
        });
      }
    
      next();
    }
    

* * *

## 5\. HTTPS and Transport Security

Always enforce HTTPS:
    
    
    const helmet = require('helmet');
    
    // Security headers
    app.use(helmet());
    
    // Force HTTPS in production
    app.use((req, res, next) => {
      if (process.env.NODE_ENV === 'production' && !req.secure) {
        return res.redirect(301, `https://${req.headers.host}${req.url}`);
      }
      next();
    });
    
    // HSTS header
    app.use(helmet.hsts({
      maxAge: 31536000, // 1 year
      includeSubDomains: true,
      preload: true
    }));
    

### Certificate Pinning (Mobile Apps)
    
    
    // React Native with certificate pinning
    import { fetch } from 'react-native-ssl-pinning';
    
    const response = await fetch('https://api.yoursite.com/data', {
      method: 'GET',
      sslPinning: {
        certs: ['cert1', 'cert2'] // Certificate names in assets
      },
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });
    

* * *

## 6\. Error Handling

Don't leak sensitive information:
    
    
    // Error handler middleware
    app.use((err, req, res, next) => {
      // Log full error internally
      console.error({
        error: err.message,
        stack: err.stack,
        path: req.path,
        method: req.method,
        userId: req.user?.userId
      });
    
      // Don't expose internal errors to clients
      if (process.env.NODE_ENV === 'production') {
        // Generic error for unknown errors
        if (!err.statusCode) {
          return res.status(500).json({
            error: 'Internal server error',
            requestId: req.id // For support reference
          });
        }
      }
    
      // Known errors with safe messages
      res.status(err.statusCode || 500).json({
        error: err.message,
        code: err.code,
        ...(process.env.NODE_ENV !== 'production' && { stack: err.stack })
      });
    });
    
    // Custom error class
    class ApiError extends Error {
      constructor(message, statusCode, code) {
        super(message);
        this.statusCode = statusCode;
        this.code = code;
      }
    }
    
    // Usage
    throw new ApiError('User not found', 404, 'USER_NOT_FOUND');
    

* * *

## 7\. CORS Configuration

Restrict cross-origin requests:
    
    
    const cors = require('cors');
    
    const corsOptions = {
      origin: (origin, callback) => {
        const allowedOrigins = [
          'https://yourapp.com',
          'https://admin.yourapp.com'
        ];
    
        // Allow requests with no origin (mobile apps, Postman)
        if (!origin) return callback(null, true);
    
        if (allowedOrigins.includes(origin)) {
          callback(null, true);
        } else {
          callback(new Error('Not allowed by CORS'));
        }
      },
      credentials: true,
      methods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'],
      allowedHeaders: ['Content-Type', 'Authorization', 'X-API-Key'],
      exposedHeaders: ['X-RateLimit-Remaining', 'X-RateLimit-Reset'],
      maxAge: 86400 // Cache preflight for 24 hours
    };
    
    app.use(cors(corsOptions));
    

* * *

## 8\. Logging and Monitoring

Comprehensive request logging:
    
    
    const winston = require('winston');
    
    const logger = winston.createLogger({
      level: 'info',
      format: winston.format.json(),
      transports: [
        new winston.transports.File({ filename: 'error.log', level: 'error' }),
        new winston.transports.File({ filename: 'combined.log' })
      ]
    });
    
    // Request logging middleware
    app.use((req, res, next) => {
      const start = Date.now();
    
      res.on('finish', () => {
        const duration = Date.now() - start;
    
        logger.info({
          method: req.method,
          path: req.path,
          statusCode: res.statusCode,
          duration,
          ip: req.ip,
          userAgent: req.headers['user-agent'],
          userId: req.user?.userId,
          apiKey: req.headers['x-api-key']?.slice(0, 8) + '...'
        });
    
        // Alert on suspicious activity
        if (res.statusCode === 401 || res.statusCode === 403) {
          logger.warn({
            type: 'AUTH_FAILURE',
            ip: req.ip,
            path: req.path,
            timestamp: new Date().toISOString()
          });
        }
      });
    
      next();
    });
    

* * *

## 9\. API Versioning

Support multiple versions securely:
    
    
    // URL versioning
    app.use('/api/v1', v1Router);
    app.use('/api/v2', v2Router);
    
    // Header versioning
    app.use('/api', (req, res, next) => {
      const version = req.headers['api-version'] || 'v1';
    
      if (version === 'v1') {
        return v1Router(req, res, next);
      } else if (version === 'v2') {
        return v2Router(req, res, next);
      }
    
      res.status(400).json({ error: 'Invalid API version' });
    });
    
    // Deprecation warnings
    app.use('/api/v1', (req, res, next) => {
      res.setHeader('Deprecation', 'true');
      res.setHeader('Sunset', 'Sat, 31 Dec 2026 23:59:59 GMT');
      res.setHeader('Link', '</api/v2>; rel="successor-version"');
      next();
    });
    

* * *

## 10\. Security Headers

Essential headers for API security:
    
    
    app.use((req, res, next) => {
      // Prevent MIME type sniffing
      res.setHeader('X-Content-Type-Options', 'nosniff');
    
      // Prevent clickjacking
      res.setHeader('X-Frame-Options', 'DENY');
    
      // XSS protection
      res.setHeader('X-XSS-Protection', '1; mode=block');
    
      // Content Security Policy
      res.setHeader('Content-Security-Policy', "default-src 'none'");
    
      // Don't cache sensitive responses
      res.setHeader('Cache-Control', 'no-store');
      res.setHeader('Pragma', 'no-cache');
    
      next();
    });
    

* * *

## Security Checklist Summary
    
    
    ## Before Deployment
    
    - [ ] HTTPS enforced (no HTTP fallback)
    - [ ] API keys/tokens not in URLs or logs
    - [ ] Input validation on all endpoints
    - [ ] SQL/NoSQL injection prevention
    - [ ] Rate limiting configured
    - [ ] CORS properly restricted
    - [ ] Security headers set
    - [ ] Error messages don't leak info
    - [ ] Authentication on all protected routes
    - [ ] Authorization (RBAC) implemented
    - [ ] Secrets in environment variables
    - [ ] Dependencies up to date
    - [ ] Security logging enabled
    - [ ] API versioning strategy
    

* * *

## Conclusion

API security requires multiple layers of protection. Start with the critical items: authentication, authorization, HTTPS, and input validation. Then add rate limiting, logging, and proper error handling.

Regular security audits and keeping dependencies updated are equally important. Use tools like OWASP ZAP or Burp Suite to test your APIs for vulnerabilities.

**Related Resources:**

  * [API Authentication Methods →](https://publicapis.io/blog/api-authentication-methods)
  * [Browse Security APIs →](https://publicapis.io/category/security)
  * [OWASP API Security Top 10 →](https://owasp.org/www-project-api-security/)



#### Supported By

These companies help keep PublicAPIs.io free and open for developers

[](https://serpapi.com/ "SerpApi - Web Search API")

[Become a sponsor →](/sponsors)

Newsletter

Get updates on new apis, and other cool stuff.

Subscribe

Explore:[API Directory](/api-directory)[API Examples](/rest-api-examples)[Blog](/blog)[Bookmarks](/collections)[Submit](/submit)

Top Categories:[Development](/category/development)[Transportation](/category/transportation)[Data access](/category/data-access)[Open data](/category/open-data)[Cryptocurrency](/category/cryptocurrency)[Geocoding](/category/geocoding)[Games and comics](/category/games-and-comics)[Media](/category/media)[Music](/category/music)

Other products:[Flyy](https://theflyy.com/)[Aikaara](https://aikaara.com/)[App Backend](https://appbackend.io/)
