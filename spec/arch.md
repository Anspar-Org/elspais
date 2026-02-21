<!-- markdownlint-disable MD009 MD041 -->
 Elspais Architecture 3.0

 elspais/                                                                                                    
 ├── cli.py                      # Entry point, argparse dispatcher                                          
 ├── __init__.py / __main__.py   # Package entry                                                             
 │                                                                                                           
 |   the graph is constructed by feeding text into a deserializer, which iteratively pulls out various nodes until all lines of the text are allocated to one and only one node
 |
 +---Graph
 │   ├── GraphNode.py            # node definitions and validation
 │   ├── relations.py            # relation (edge) definitions and validation
 │   ├── annotators.py           # Graph annotation functions
 │   ├── DomainDeserializer.py   # abstract controller for text -> graph objects. controls iterating over its domain and passing the domain context (e.g. filename, 'stdio', 'cli') and text to the parser.
 |   |   +-- DomainFile.py       # directory / file deserializer.  Uses config to include/exclude certain dir and file types. Can enable/disable parsing of different node types based on the directory or file type.
 |   |   +-- DomainStdio.py      # stdio deserializer
 |   |   '-- DomainCLI.py        # CLI argument deserializer
 │   ├── serialize.py            # Centralized controller for graph -> other formats
 |   +-- MDparser.py             # abstract class, one instance for each node type. markdown format. finds boundaries of its node type and parses its properties. iterates over all nodes types in priority order, each nodetype claiming lines of text and creating Nodes. Next parser does not see lines already claimed.
 |       +-- comments.py             # first find all comment blocks (various languages)
 |       +-- heredocs.py             # then all variables and heredocs (mock data)
 |       +-- requirement.py          # remainder of source gets parsed into these types of nodes
 |       |   '-- assertions.py       # one of the few 'subnodes' within another node 
 │       ├── journey.py              # User journey parser
 │       ├── code.py                 # Code reference parser (# Implements:)                                     
 │       ├── test.py                 # Test file parser (Validates:)                                             
 |       '-- results.py              # results nodes
 |       |   ├── junit_xml.py        # JUnit XML results
 │       |   └── pytest_json.py      # pytest JSON results
 |       '-- remainder.py            # any lines of text not claimed by other nodes gets put into remainder nodes. These have only consecutive lines, so there may be many remainders per deserialized text input
 |
 |
 |      Graph parts to be refactored into the above if needed:
 |          │   ├── graph.py                # TraceGraph, TraceNode, NodeKind                                           
 |          │   ├── graph_builder.py        # TraceGraphBuilder - builds/validates graph                                
 │          ├── graph_schema.py         # Schema definitions, RollupMetrics                                         
 │          ├── rules.py                # RuleEngine - validation rules library                                     
 |
 |
 |--Utlities
 │   ├── git.py                  # Git change detection                                                      
 │   ├── hasher.py               # Hash calculation utilities                                                RequirementParser - parses Markdown                                       
 |---+-- patterns.py             # library for defining and matching patterns as defined in config
 │   ├── diff.py                 # Diff utilities                                                            

 ├── commands/                   # CLI IMPLEMENTATIONS (thin wrappers)                                       
 │   ├── validate.py             # elspais validate                                                          
 │   ├── trace.py                # elspais trace                                                             
 │   ├── analyze.py              # elspais analyze                                                           
 │   ├── fix_cmd.py              # elspais fix                                                              
 │   ├── changed.py              # elspais changed                                                           
 │   ├── index.py                # elspais index                                                             
 │   ├── edit.py                 # elspais edit                                                              
 │   ├── init.py                 # elspais init                                                              
 │   ├── config_cmd.py           # elspais config                                                            
 │   ├── rules_cmd.py            # elspais rules                                                             
 │   ├── example_cmd.py          # elspais example                                                           
 │   └── reformat_cmd.py         # elspais reformat-with-claude                                              
 │                                                                                                           
 ├── config/                     # CONFIGURATION                                                             
 |   |  ConfigLoader.py          # Abstract config loader. Handles when config can be set (only before Graph is parsed). 
 │   |  ├── LoaderFile.py        # TOML parser, config discovery
 |   |  +-- LoaderStdio.py       # strips toml config from beginning of stdio if present 
 |   |  +-- LoaderCLI.py         # for setting via command line
 |   |  +-- LoaderAPI.py         # for config via API (MCP, other interactive tool)
 │   └── defaults.py             # Default config values                                                     

 }|  Unclear what this is for. Possibly utility, possibly not needed.
 │   └── content_rules.py        # AI agent content rules                                                    
 │                                                                                                           
 ├── testing/                    # TEST COVERAGE                                                             
 │   ├── mapper.py               # TestCoverageMapper - uses Graph traverse composition to apply coverage attributes to nodes
 │                                                                                                           
 ├── associates/                 # MULTI-REPO (consolidate with config?)
 │   └── __init__.py             # Associate config loading 
 │                                                                                                           
 ├── reformat/                   # AI REFORMATTING                                                           
 │   ├── detector.py             # Format detection                                                          
 │   ├── transformer.py          # Claude CLI integration                                                    
 │   ├── prompts.py              # System prompts                                                            
 │   └── line_breaks.py          # Line break normalization                                                  
 │                                                                                                           
 ├── trace/                      # VISUALIZATION (optional: trace-view extra)                                
 │   ├── models.py               # TraceViewRequirement adapter (obsolete?)
 │   '── generators/             # Output generators (should compose with Graph)
 │       ├── base.py             # TraceViewGenerator                                                        
 │       ├── csv.py              # CSV export                                                                
 │       +── markdown.py         # Markdown matrix                                                           
 │       └── html.py             # HTML generation (requires jinja2)                                         
 |
 │── review/                 # Review server (requires flask)                                            
 │   ├── server.py           # Flask REST API                                                            
 │   ├── models.py           # Comment, Thread, ReviewFlag                                               
 │   ├── storage.py          # JSON persistence                                                          
 │   ├── branches.py         # Git branch management                                                     
 │   ├── position.py         # Position resolution                                                       
 │   └── status.py           # Requirement status modification                                           
 │                                                                                                           
 └── mcp/                        # MCP SERVER (optional: mcp extra)                                          
     ├── server.py               # MCP resources and tools                                                   
     ├── context.py              # WorkspaceContext, GraphState                                              
     ├── serializers.py          # JSON serialization
     ├── mutator.py              # Spec file mutations                                                       
     ├── transforms.py           # AI transformations                            
     ├── annotations.py          # Session annotations (should use Graph annotate)
     ├── git_safety.py           # Safety branches                                                           
     └── reconstructor.py        # File reconstruction (should be trivial from traversing a full Graph, as the nodes contain a complete list files and line numbers, at least for a fully parsed input)
