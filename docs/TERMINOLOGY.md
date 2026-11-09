# CHARM matrix multiplication terminology

Concepts used in code explanations. Implementation and verification details
belong in the [porting notes](porting_plan/README.md).

## Language

**Input matrix B**:
The right operand of matrix multiplication AB. Distinct from graph parameter B.

**Configuration B / cascade length**:
The number of AIE kernel instances that divide the K dimension for one output tile.
_Avoid_: Input matrix B, number of kernel types

**Output tile**:
A submatrix comprising a subset of rows and cols of the complete result C.

**K-dimension partial product**:
A matrix product over part of the reduction dimension, summed with other partial
products to form the same output tile.
_Avoid_: Separate output tiles

**Cascade partial sum**:
An intermediate sum passed between AIEs as they accumulate K-dimension products.

**Kernel role**:
A function's responsibility as the initial, intermediate, final or standalone
stage of computation.
_Avoid_: Physical AIE number, layer number

**Kernel instance**:
An individual execution unit in a graph. Multiple instances can share a role.

**AIE tile**:
A hardware processing unit within the AI Engine array.
_Avoid_: Matrix tile, output tile

**CHARM AIE generation path**:
The configuration-driven path that generates kernels, cascade graphs, top-level
graphs and their connections together.
_Avoid_: A harness that only renders individual kernel templates

**AIE simulation verification**:
Executing the generated graph in the AIE simulator and comparing actual output
against a reference.
_Avoid_: Generation success, compilation success, reference preparation alone
