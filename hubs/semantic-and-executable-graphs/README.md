# Semantic and executable graphs

An unsigned sample, derived from the two named sections of the public TRUGS paper
and its bibliography at revision `37bb78c781adba7fa6a759e4688feb1b2e29c604`.
Bindings retain the citation title, address and digest beside the core TRL.
The graph includes those fields for offline queries; they do not survive core TRL conversion.

```trl
MODULE semantic_memory REFERENCES RESOURCE quillian1968semantic.
MODULE semantic_web REFERENCES RESOURCE berners2001semantic.
MODULE ontologies REFERENCES RESOURCE gruber1993translation.
MODULE rdf REFERENCES RESOURCE rdf2014.
MODULE owl REFERENCES RESOURCE owl2012.
MODULE petri_nets REFERENCES RESOURCE petri1962kommunikation.
MODULE parallel_graphs REFERENCES RESOURCE karp1966properties.
MODULE dataflow REFERENCES RESOURCE dennis1975preliminary.
MODULE actors REFERENCES RESOURCE hewitt1973universal.
MODULE statecharts REFERENCES RESOURCE harel1987statecharts.
MODULE tensorflow REFERENCES RESOURCE abadi2016tensorflow.
MODULE spark REFERENCES RESOURCE zaharia2012resilient.
MODULE controlled_languages REFERENCES RESOURCE kuhn2014survey.
MODULE ace REFERENCES RESOURCE fuchs2008attempto.
MODULE attempto REFERENCES RESOURCE schwitter1996attempto.
MODULE cpl REFERENCES RESOURCE clark2005class.
MODULE peng REFERENCES RESOURCE schwitter2002english.
MODULE formal_semantics REFERENCES RESOURCE montague1973proper.
MODULE sydney_owl REFERENCES RESOURCE cregan2007sydney.
MODULE answer_sets REFERENCES RESOURCE schwitter2018asp.
MODULE owl_services REFERENCES RESOURCE owls2004.
MODULE opm REFERENCES RESOURCE yaroker2013opm.
MODULE opcat REFERENCES RESOURCE dori2003opcat.
MODULE exekg REFERENCES RESOURCE zheng2022executable.
MODULE model_extraction REFERENCES RESOURCE bian2025llm.
MODULE models_and_graphs REFERENCES RESOURCE pan2024unifying.
MODULE json_ld REFERENCES RESOURCE jsonld2020.
MODULE property_graphs REFERENCES RESOURCE neo4j.
MODULE mcp REFERENCES RESOURCE mcp2025.
MODULE langgraph REFERENCES RESOURCE langgraph2024.
MODULE autogen REFERENCES RESOURCE wu2023autogen.
MODULE crewai REFERENCES RESOURCE crewai2023.
MODULE dspy REFERENCES RESOURCE khattab2024dspy.
MODULE guided_generation REFERENCES RESOURCE willard2023efficient.
MODULE slot REFERENCES RESOURCE tam2025slot.
MODULE owl EXTENDS MODULE rdf.
MODULE exekg REFERENCES MODULE owl.
MODULE trugs REFERENCES MODULE controlled_languages.
MODULE trugs REFERENCES MODULE dataflow.
MODULE trugs REFERENCES MODULE semantic_web.
```

| System | Strength | Gap |
| --- | --- | --- |
| Semantic Memory | Networks express associations between concepts. | They do not specify operations or obligations. |
| Semantic Web | Shared identifiers and linked statements support knowledge exchange. | Execution needs separate programs. |
| Ontologies | Shared conceptual descriptions support reuse. | An ontology alone does not order computation. |
| Rdf | A standard graph data model supports exchange and traversal. | It does not provide an instruction language. |
| Owl | Ontology logic enables inference over semantic statements. | Inference and general operations remain distinct. |
| Petri Nets | Transition firing makes a graph computational. | Operations do not carry the semantic vocabulary of knowledge graphs. |
| Parallel Graphs | Graph models support reasoning about parallel computation. | They do not provide controlled English or obligations. |
| Dataflow | The graph directly defines the flow of computation. | Operations remain opaque to a shared semantic vocabulary. |
| Actors | Message-passing agents provide a graph model of computation. | Message content is not a closed semantic language. |
| Statecharts | A visual graph can be readable and executable. | It does not provide the semantic graph language described here. |
| Tensorflow | Computation graphs scale dataflow execution. | Operation meanings are supplied separately from the graph. |
| Spark | Distributed dataflow graphs support large computations. | The graph does not type the meaning of its instructions as controlled English. |
| Controlled Languages | Controlled languages demonstrate precise constrained natural language. | The surveyed tradition commonly targets logic rather than a mutable general graph. |
| Ace | Constrained English can represent knowledge unambiguously and support OWL translation. | The cited approach targets logic rather than a general graph of operations. |
| Attempto | English specifications produce queryable Prolog for simulation and validation. | The Prolog is not decompiled back to the authored sentence. |
| Cpl | Restricted English supports acquiring and using knowledge. | Its knowledge target is not the typed general graph used here. |
| Peng | English can serve as a formal specification surface. | The paper places it in the logic-targeted language tradition. |
| Formal Semantics | Compositional semantics links language to precise formal meaning. | Logical representations are not directly the operational graph. |
| Sydney Owl | Controlled language maps bidirectionally to OWL. | The target is ontology logic rather than a general graph of computation. |
| Answer Sets | Programs can be specified and verbalised with semantic round trips. | The target is a logic program and the round trip is semantic rather than token-preserving. |
| Owl Services | Semantic descriptions support discovery, invocation and composition of services. | There is no controlled-language sentence surface or sentence decompilation. |
| Opm | One diagram integrates structure and behavior and supports executable simulation. | Text is generated from diagrams; the vocabulary lacks obligation and permission modalities. |
| Opcat | A bimodal tool supports object-process models. | The diagram is authored first; it lacks typed deontic edges. |
| Exekg | Semantic machine-learning pipelines translate into executable Python. | The GUI-authored approach is specific to analytics and carries no obligations. |
| Model Extraction | Language models help build graphs from unstructured sources. | Extraction stages can lose information and require schema and knowledge fusion. |
| Models And Graphs | Models and knowledge graphs can complement each other. | Extraction does not itself eliminate the representation gap. |
| Json Ld | A standard linked-data representation supports precise exchange. | Direct authoring still commonly needs translation tools. |
| Property Graphs | Properties and relations support flexible graph storage. | The storage model is not a constrained English surface. |
| Mcp | A protocol standardizes tool requests and responses. | Communication mechanics do not establish shared word meanings. |
| Langgraph | State-machine graphs organize model workflows. | Node content remains code or opaque natural language. |
| Autogen | Conversation topology organizes cooperating agents. | The topology does not type the meaning of their content. |
| Crewai | Role hierarchies organize agent work. | The hierarchy does not define a closed semantic language for instructions. |
| Dspy | Typed signatures and declarative modules give pipelines semantic structure. | Semantics are at module granularity rather than every instruction word. |
| Guided Generation | Constrained decoding enforces structured output syntax. | Valid structure alone does not ensure valid meaning. |
| Slot | Structured generation improves output format compliance. | Format compliance alone does not validate semantic combinations. |
| TRUGS | Controlled English compiles to a typed general graph with a syntactic round trip and typed obligations. | It requires a closed vocabulary and valid compositions; extraction from arbitrary prose still needs a separate process. This sample uses core relations, is unsigned, and does not implement the draft hub services. |

Source resources and their bibliography keys are in [bindings.json](bindings.json).
The sample describes differences; it does not assign endorsements or rankings.
TRUGS is one system in this history. No signed publisher service is implied.
