# Onshape MCP Knowledge Base

This knowledge base provides comprehensive documentation for creating CAD expert AI agents that understand Onshape API and professional CAD practices.

## Structure

```
knowledge_base/
├── api/                    # Onshape REST API documentation
│   └── onshape_api_overview.md
├── cad/                    # CAD principles and best practices
│   └── cad_best_practices.md
├── examples/               # Real-world design examples
│   └── parametric_bracket.md
└── README.md              # This file
```

## How This Works

### For AI Agents

The knowledge base files serve as:

1. **Reference Material** - Quick lookups for API syntax and CAD patterns
2. **Training Examples** - Real-world scenarios and solutions
3. **Best Practices** - Professional guidelines and standards
4. **Design Patterns** - Reusable approaches to common problems

### Integration Methods

#### Option 1: MCP Resources (Recommended)

Add to your `server.py`:

```python
@app.list_resources()
async def list_resources() -> list[Resource]:
    """Provide knowledge base as MCP resources."""
    resources = []
    kb_path = Path(__file__).parent.parent / "knowledge_base"

    for md_file in kb_path.glob("**/*.md"):
        if md_file.name == "README.md":
            continue

        relative_path = md_file.relative_to(kb_path)
        resources.append(Resource(
            uri=f"onshape://kb/{relative_path}",
            name=md_file.stem.replace('_', ' ').title(),
            description=f"Knowledge: {md_file.stem}",
            mimeType="text/markdown"
        ))

    return resources

@app.read_resource()
async def read_resource(uri: str) -> str:
    """Read knowledge base content."""
    if not uri.startswith("onshape://kb/"):
        raise ValueError("Invalid resource URI")

    kb_path = Path(__file__).parent.parent / "knowledge_base"
    file_path = kb_path / uri.replace("onshape://kb/", "")

    if not file_path.exists():
        raise FileNotFoundError(f"Resource not found: {uri}")

    return file_path.read_text()
```

Claude can then read these files during conversations!

#### Option 2: Claude Projects

If you have Claude Pro/Teams:
1. Create a project called "Onshape CAD Expert"
2. Upload all `.md` files from this knowledge base
3. Claude has access to all content in every conversation

#### Option 3: System Prompts

Reference key content in your system prompt:

```markdown
You have access to comprehensive Onshape knowledge:

- API Overview: Complete REST API reference
- CAD Best Practices: Professional CAD guidelines
- Design Examples: Real-world parametric designs

Refer to these resources when:
- Users ask about API usage
- Designing new features
- Following best practices
- Creating parametric models
```

## Content Overview

### `/api` - Onshape REST API

**onshape_api_overview.md**
- API structure and authentication
- Document hierarchy (document → workspace → element)
- Key endpoints for all operations
- Feature JSON structure reference
- Parameter types and examples
- Variables and expressions syntax
- Common patterns and best practices
- Standard plane IDs and queries

**What It Covers:**
- ✅ All major API endpoints
- ✅ JSON structure for features
- ✅ Variable and expression syntax
- ✅ Query types and references
- ✅ Common patterns
- ✅ Error handling

### `/cad` - CAD Principles

**cad_best_practices.md**
- Parametric design principles
- Design intent documentation
- Feature organization strategies
- Sketch best practices
- Variable usage guidelines
- Pattern creation
- Fillet and chamfer strategies
- Design for Manufacturing (DFM)
- Performance optimization
- Assembly best practices
- Common mistakes to avoid

**What It Covers:**
- ✅ Professional CAD workflows
- ✅ Parametric modeling techniques
- ✅ Feature naming and organization
- ✅ Manufacturing considerations
- ✅ Material-specific guidelines
- ✅ Quality checklists

### `/examples` - Real Designs

**parametric_bracket.md**
- Complete L-bracket design
- Variable table with descriptions
- Full feature sequence
- Design validation tests
- Manufacturing notes
- Design variations
- Key takeaways

**What It Covers:**
- ✅ End-to-end design example
- ✅ Complete variable table
- ✅ Logical feature sequence
- ✅ Testing and validation
- ✅ Manufacturing process
- ✅ Design variations

## Expanding the Knowledge Base

### Adding New Content

1. **API Documentation**
   ```bash
   # Add new API endpoint docs
   knowledge_base/api/assemblies_api.md
   knowledge_base/api/drawings_api.md
   knowledge_base/api/metadata_api.md
   ```

2. **CAD Guides**
   ```bash
   # Add specific CAD topics
   knowledge_base/cad/sheet_metal_design.md
   knowledge_base/cad/plastic_part_design.md
   knowledge_base/cad/assembly_strategies.md
   ```

3. **Examples**
   ```bash
   # Add more design examples
   knowledge_base/examples/enclosure_design.md
   knowledge_base/examples/gear_assembly.md
   knowledge_base/examples/sheet_metal_box.md
   ```

### Content Guidelines

**Good Knowledge Base Content:**
- ✅ Accurate and tested
- ✅ Well-organized with clear headers
- ✅ Includes code examples
- ✅ Explains the "why" not just "how"
- ✅ Covers edge cases
- ✅ Includes best practices
- ✅ References official docs

**Content Template:**
```markdown
# Topic Name

## Overview
Brief description of what this covers

## Key Concepts
Main ideas and principles

## Syntax/Structure
How to use it (with examples)

## Examples
Real-world usage examples

## Best Practices
Professional guidelines

## Common Mistakes
What to avoid

## Resources
Links to official docs
```

## Scraping Onshape Documentation

To add official Onshape docs:

```python
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify

def scrape_onshape_page(url: str, output_file: str):
    """Scrape and convert Onshape docs to markdown."""
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    # Extract main content
    content = soup.find('main') or soup.find('article')

    # Convert to markdown
    markdown = markdownify(str(content))

    # Save
    Path(output_file).write_text(markdown)

# Scrape key pages
pages = {
    "api-intro": "https://onshape-public.github.io/docs/api-intro/",
    "partstudios": "https://onshape-public.github.io/docs/partstudios/",
    # Add more...
}

for name, url in pages.items():
    scrape_onshape_page(url, f"knowledge_base/api/{name}.md")
```

## Using with RAG (Advanced)

For semantic search over large documentation:

```python
from sentence_transformers import SentenceTransformer
import faiss

class KnowledgeBaseRAG:
    def __init__(self, kb_path: str):
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.index_knowledge_base(kb_path)

    def index_knowledge_base(self, kb_path: str):
        """Create embeddings for all docs."""
        texts = []
        for md_file in Path(kb_path).glob("**/*.md"):
            content = md_file.read_text()
            # Split into chunks
            chunks = self.chunk_text(content, chunk_size=500)
            texts.extend(chunks)

        # Create FAISS index
        embeddings = self.model.encode(texts)
        self.index = faiss.IndexFlatL2(embeddings.shape[1])
        self.index.add(embeddings)
        self.docs = texts

    def search(self, query: str, k: int = 3):
        """Find relevant documentation."""
        query_emb = self.model.encode([query])
        distances, indices = self.index.search(query_emb, k)

        return [self.docs[i] for i in indices[0]]
```

## Maintenance

### Regular Updates

1. **Monthly Review**
   - Check for API changes
   - Update deprecated patterns
   - Add new features

2. **User Feedback**
   - Add frequently asked topics
   - Clarify confusing sections
   - Expand examples

3. **Onshape Releases**
   - Review release notes
   - Update affected docs
   - Add new capabilities

### Quality Checks

- [ ] All code examples tested
- [ ] Links to official docs valid
- [ ] Markdown formatting correct
- [ ] Consistent terminology
- [ ] No outdated information

## Contributing

To add content:

1. Choose appropriate directory (`api/`, `cad/`, or `examples/`)
2. Create `.md` file with descriptive name
3. Follow content template
4. Include code examples
5. Add references to official docs
6. Test all examples
7. Update this README if adding new category

## Resources

### Official Onshape
- [API Documentation](https://onshape-public.github.io/docs/)
- [Developer Portal](https://dev-portal.onshape.com/)
- [FeatureScript Docs](https://cad.onshape.com/FsDoc/)
- [Learning Center](https://learn.onshape.com/)
- [Forum](https://forum.onshape.com/)

### CAD Resources
- Professional CAD standards (ASME Y14.5, ISO 128)
- Manufacturing process guides
- Material specifications
- Industry best practices

### AI/MCP
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Claude Documentation](https://docs.anthropic.com/)
- [Prompt Engineering](https://docs.anthropic.com/claude/docs/prompt-engineering)

## Next Steps

1. **Start Using**: Reference this KB when helping users
2. **Expand Content**: Add more examples and guides
3. **Implement RAG**: Add semantic search for large docs
4. **Gather Feedback**: Learn what content is most useful
5. **Keep Updated**: Maintain as Onshape evolves

The knowledge base is a living resource that grows with your needs!
