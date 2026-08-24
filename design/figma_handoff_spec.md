# SmartRoute AI Product UI Handoff

This is a Figma-ready product design package for SmartRoute AI. Since the Figma connector is not available in the current Codex settings, the design is delivered as a local high-fidelity HTML board plus this implementation spec.

## Files

- `smartroute_product_ui.html`: high-fidelity dual-end design board.
- `figma_handoff_spec.md`: design tokens, component notes, and implementation mapping.

## Product Positioning

SmartRoute AI is not a replacement for XiaoTuan AI. It is a route-planning sub-agent that converts recommended POIs into executable plans under real constraints: time, budget, queue risk, walking intensity, business hours, and personal preference memory.

## Visual Direction

- Style: Meituan-native product concept.
- Primary color: `#FFD100`.
- Text: `#111111`, `#222222`, `#777777`.
- Surface: `#F6F6F6`, `#FFFFFF`.
- Radius: 14, 18, 22, 28, 42.
- Shadow: soft product cards, not dashboard-heavy.

## Mobile Screens

1. Home / AI input
2. Constraint confirmation
3. Route result
4. Route detail and explanation
5. Replace POI
6. In-trip assistant
7. Feedback and memory

## Desktop Screens

1. Hackathon Demo Cockpit
2. Route Compare
3. POI / Constraint Explanation

## Components

- Button: primary yellow, secondary black.
- Chip: default, yellow selected, green success, red risk.
- Route Card: title, confidence score, four metrics.
- POI Card: order, title, meta, reason, transit.
- Timeline Node: stop order, POI name, time, status.
- Replace POI Card: candidate, delta time, delta budget, queue risk.
- Map Marker: numbered black pin with yellow number.

## Data Mapping

| UI Element | Backend Model |
|---|---|
| Time, budget, queue, walking constraints | `UserConstraints` |
| POI title, price, rating, wait, tags | `POI` |
| Timeline stop | `RouteStop` |
| Route metrics | `Route` |
| Likes / dislikes / history | `UserProfile` |
| Explanation text | `Route.highlights`, `Route.warnings`, route validation rules |

## Next Figma Steps

When Figma becomes available:

1. Create file `SmartRoute AI Product UI`.
2. Create pages: `00 Cover`, `01 Mobile App`, `02 Desktop Demo`, `03 Components`, `04 Interaction Notes`.
3. Recreate the HTML board screens as frames:
   - Mobile frames: `390 x 844`.
   - Desktop frames: `1440 x 900`.
4. Use the token values above for variables.
5. Convert repeated cards/chips/buttons into Figma components.
