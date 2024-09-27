This repository contains the code for our paper : [WikiCoder: Learning to Write
Knowledge-Powered Code](https://rdcu.be/dITGA).

This is joint work of [Théo Matricon](theomath.github.io), [Nathanaël Fijalkow](https://nathanael-fijalkow.github.io/) and [Gaëtan Margueritte](https://github.com/gaetanmargueritte).

It is based on an old version of [ProgSynth](https://github.com/Theomat/ProgSynth) our program synthesis tool.


<!-- toc -->

- [More About ProgSynth](#more-about-progsynth)
  - [Combining Deep Learning with Theoretical Guarantees](#combining-deep-learning-with-theoretical-guarantees)
  - [A Scalable Framework](#a-scalable-framework)
- [Installation](#installation)
  - [From Source](#from-source)
    - [Install ProgSynth](#install-progsynth)
- [Documentation](#documentation)
- [Troubleshooting](#troubleshooting)
- [Examples](./examples)
- [The Team](#the-team)
- [License](#license)

<!-- tocstop -->

## More About ProgSynth

At a granular level, ProgSynth is a library that consists of the following components:

| Component | Description |
| ---- | --- |
| [**synth**](./synth) | A high level synthesis libary |
| [**synth.generation**](./synth/generation) | A compilation of tools to generate objetcs needed for the synthesis, it is mainly used with deep learning  |
| [**synth.nn**](./synth/nn) | A library to build neural network with for synthesis  |
| [**synth.pbe**](./synth/pbe) | A library to work in the Programming By Example (PBE) framework |
| [**synth.pruning**](./synth/pruning) | A library with pruning strategies |
| [**synth.semantic**](./synth/semantic) | A library of program evaluators |
| [**synth.syntax**](./synth/syntax) | A library to manipulate dsl, grammars, probabilistic grammars |
| [**synth.utils**](./synth/utils) | Utility objects and functions that do not fit elsewhere |

Elaborating Further:

### Combining Deep Learning with Theoretical Guarantees

The advantage of "classic" algorithms are their theoretical guarantees.
But many new deep learning based methods have emerged, they provide a tremendous efficiency but lose almost all theoretical guarantees.
ProgSynth provides already implemented algorithms that combine both approaches to get the best of both worlds: speed and guarantees!

### A Scalable Framework

Computing is now done at a large scale in a parallelilized fashion.
As such frameworks should also adapt: they should scale with more computing power but also leverage the power of parallelization.
This was taken into account and this is why for most algorithms we provide, we also provide a way to scale with the number of available processors.

For example, you can split probabilistic grammars into disjoint sub grammars to split the enumeration of the grammar into multiple jobs thus enabling to scale linearly with the numbers of workers.

## Installation

### From Source

If you are installing from source, you will need Python 3.7.1 or later.

#### Install ProgSynth

ProgSynth can be installed from source with `pip`, `conda` or `poetry`.

```bash
pip install .
```

## Documentation

You might want to generate html pages of the documentation locally, where usage, contribution guidelines and more can be found.
In which case, you will need to use [Sphinx](https://www.sphinx-doc.org/en/master/). 

```bash
pip install sphinx sphinx-rtd-theme myst-parser
```

If Sphinx installation was successful, then use the following command line to generate html pages that you can view by opening the file `docs/build/html/index.html` in your favorite web browser.

```bash
sphinx-build -b html docs/source docs/build/html
```

## Troubleshooting

There are some known issues:

- **seed = 0** is the **same as no seeding**.
- if you get an error after installation try to update/upgrade ``numpy``, it is often due to a discrepancy between the version with which ``vose`` is compiled and the version the environment is running.
- some dependencies may be missing depending on the DSL you want to use, running any example script with -h will ist you the list of available DSL with your current installation.

## The Team

ProgSynth is a project initiated by [Nathanaël Fijalkow](https://nathanael-fijalkow.github.io/) and joined by [Théo Matricon](https://theomat.github.io/).

Former:

- [Gaëtan Margueritte](https://github.com/gaetanmargueritte) did a four-month internship. He created the regexp and transduction DSLs, the first tutorial and first drafts of code related to the use of user defined constants.

## License

ProgSynth has a MIT license, as found in the [LICENSE](LICENSE) file.
