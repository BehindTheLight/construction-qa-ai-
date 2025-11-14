# Demo Chat Frontend

ChatGPT-style web interface for the Demo construction document AI assistant.

## Quick Start

```bash
# 1. Install Node.js (if not installed)
brew install node

# 2. Install dependencies
npm install

# 3. Create .env.local (if not exists)
echo "NEXT_PUBLIC_API_BASE=http://localhost:8000" > .env.local

# 4. Start the development server
npm run dev

# 5. Open in browser
open http://localhost:3000
```

## Features

- ChatGPT-style interface with dark sidebar
- Conversation history and management
- Real-time chat with AI assistant
- Citations with PDF page links
- Document search interface
- Multi-project support
- Responsive design

## Tech Stack

- **Next.js 14** - React framework with App Router
- **TypeScript** - Type-safe JavaScript
- **Tailwind CSS** - Utility-first styling
- **Axios** - HTTP client for API calls

## Project Structure

```
/app
├── /app                      # Next.js pages (App Router)
│   ├── layout.tsx            # Root layout
│   ├── page.tsx              # Home (redirects to /chat)
│   ├── globals.css           # Global styles
│   ├── /chat
│   │   └── page.tsx          # Main chat interface
│   └── /search
│       └── page.tsx          # Search interface
├── /components               # React components
│   ├── Sidebar.tsx           # Conversation list
│   ├── Chat.tsx              # Chat area
│   └── Message.tsx           # Message bubbles
├── /lib                      # Utilities
│   ├── api.ts                # API client
│   ├── types.ts              # TypeScript types
│   └── env.ts                # Environment config
├── package.json              # Dependencies
├── tsconfig.json             # TypeScript config
├── tailwind.config.js        # Tailwind config
└── .env.local                # Environment variables (git-ignored)
```

## Available Scripts

```bash
# Development server (with hot reload)
npm run dev

# Production build
npm run build

# Start production server
npm run start

# Lint code
npm run lint
```

## Environment Variables

Create `.env.local` with:

```bash
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

For production, change to your API domain:

```bash
NEXT_PUBLIC_API_BASE=https://your-api-domain.com
```

## Usage

### Creating a Conversation

1. Click "+ New chat" in the sidebar
2. Type your question in the input box
3. Press Enter or click Send
4. AI response appears with citations

### Switching Conversations

1. Click on any conversation in the sidebar
2. Message history loads automatically
3. Continue chatting from where you left off

### Using Citations

1. Click on citation badges (e.g., "p.3 · doc_abc")
2. Opens new tab with PDF viewer URL
3. Note: PDF viewer UI not implemented yet

### Searching Documents

1. Navigate to http://localhost:3000/search
2. Enter search query
3. View results with scores and metadata

## Development

### Adding New Components

```bash
# Create component file
touch components/NewComponent.tsx
```

```tsx
// components/NewComponent.tsx
export default function NewComponent() {
  return <div>Hello!</div>;
}
```

### Adding New Pages

```bash
# Create page directory and file
mkdir -p app/new-page
touch app/new-page/page.tsx
```

```tsx
// app/new-page/page.tsx
export default function NewPage() {
  return <div>New Page</div>;
}
```

Access at: `http://localhost:3000/new-page`

### Styling with Tailwind

Use Tailwind utility classes directly in JSX:

```tsx
<div className="bg-blue-600 text-white rounded-lg px-4 py-2">
  Button
</div>
```

## API Integration

The frontend calls these FastAPI endpoints:

| Endpoint | Purpose |
|----------|---------|
| `POST /conversations` | Create new conversation |
| `GET /conversations?project_id=X` | List conversations |
| `GET /conversations/{id}/messages` | Get message history |
| `POST /conversations/{id}/messages` | Save message |
| `POST /qa` | Ask question |
| `GET /search` | Search documents |

See `lib/api.ts` for implementation.

## Troubleshooting

### Port 3000 in use

```bash
# Use different port
npm run dev -- -p 3001
```

### "Failed to load conversations"

- Ensure FastAPI is running on port 8000
- Check browser console for errors
- Verify `.env.local` has correct API_BASE

### Styles not loading

```bash
# Delete .next cache and restart
rm -rf .next
npm run dev
```

### npm command not found

```bash
# Install Node.js
brew install node
```

## Production Deployment

### Build for production

```bash
npm run build
```

### Deploy to Vercel (recommended)

1. Push code to GitHub
2. Import project in Vercel
3. Set environment variable: `NEXT_PUBLIC_API_BASE=https://your-api.com`
4. Deploy

### Deploy to other platforms

- **Netlify:** `npm run build && netlify deploy`
- **AWS Amplify:** Follow Amplify docs for Next.js
- **Self-hosted:** `npm run build && npm run start`

## Performance

- Initial load: 1-2 seconds
- Navigation: <200ms (client-side routing)
- Chat latency: 1.3-2.5s (API latency)
- Search: 400-800ms (API latency)

## Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Contributing

1. Make changes in a feature branch
2. Test locally with `npm run dev`
3. Build to check for errors: `npm run build`
4. Submit pull request

## License

Internal project - All rights reserved

## Support

- Full setup guide: `/STEP7_FRONTEND_SETUP.md`
- API documentation: http://localhost:8000/docs
- Backend code: `/api`

