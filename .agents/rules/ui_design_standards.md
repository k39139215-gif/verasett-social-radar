# UI & Design Engineering Standards Rule

Whenever you are asked to build, design, modify, review, or style any user interface, frontend component, dashboard, website, or mobile screen:

1. **Default Craft Standard (Apple & Emil Kowalski Design Engineering):**
   - Automatically adhere to the principles of Apple Design (pple-design) and Emil Kowalski Design Engineering (emil-design-eng, nimate).
   - Eliminate amateur tells: Avoid flat, lifeless, generic AI-generated Tailwind/HTML.
   - Enforce craft details: Immediate pointer-down feedback, physics-based springs (not stiff linear easing), subtle depth and border radius hierarchy, disciplined optical typography, translucent glass/materials, and responsive micro-interactions.

2. **Design Repository Vault & Components:**
   - Locate and leverage patterns from the local Design Vault:
     - Check local workspace: .agents/rules/, .agents/skills/, or embedded design components.
     - Check local machine vault:
       - Windows: %USERPROFILE%\Desktop\Top_Design_Repos\ or %USERPROFILE%\.design-vault\
       - Mac/Linux: ~/Desktop/Top_Design_Repos/ or ~/.design-vault/
   - When building interactive components, refer to and leverage the patterns from these repositories:
     - magicui-components/: Bento grids, animated beam, border glow, particle backdrops, and interactive cards.
     - shadcn-ui/: Clean accessible component primitives and structure.
     - emilkowalski-vaul/: Physics-based drawer and sheet components.
     - emilkowalski-sonner/: Polished toast notifications.
     - cmdk-spotlight-menu/: Apple Spotlight / Raycast / Linear style command palette.
     - 	remor-dashboard-ui/: Enterprise dashboard metrics, analytics, and clean KPI cards.
     - craft-background-snippets/: Radial glow gradients and modern subtle dark-mode grid patterns.
     - emilkowalski-skills/: Apple design guidelines and animation rules.
