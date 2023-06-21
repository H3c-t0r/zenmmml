#  Copyright (c) ZenML GmbH 2021. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:
#
#       https://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
#  or implied. See the License for the specific language governing
#  permissions and limitations under the License.

"""Utility functions and classes to run ZenML steps."""

import ast
import inspect
import textwrap
import typing
from typing import Annotated, Any, Callable, Dict, Optional, Tuple, Union

import pydantic.typing as pydantic_typing

from zenml.logger import get_logger
from zenml.steps.step_output import Output
from zenml.utils import source_code_utils

logger = get_logger(__name__)

SINGLE_RETURN_OUT_NAME = "output"


def get_args(obj: Any) -> Tuple[Any, ...]:
    """Get arguments of a Union type annotation.

    Example:
        `get_args(Union[int, str]) == (int, str)`

    Args:
        obj: The annotation.

    Returns:
        The args of the Union annotation.
    """
    return tuple(
        pydantic_typing.get_origin(v) or v
        for v in pydantic_typing.get_args(obj)
    )


def parse_return_type_annotations(func: Callable[..., Any]) -> Dict[str, Any]:
    """Parse the return type annotation of a step function.

    Args:
        func: The step function.

    Raises:
        RuntimeError: If the output annotation has variable length or contains
            duplicate output names.

    Returns:
        The function output artifacts.
    """
    signature = inspect.signature(func, follow_wrapped=True)
    return_annotation = signature.return_annotation

    if return_annotation is None:
        return {}

    if return_annotation is signature.empty:
        if has_only_none_returns(func):
            return {}
        else:
            return_annotation = Any

    if isinstance(return_annotation, Output):
        return {
            output_name: resolve_type_annotation(output_type)
            for output_name, output_type in return_annotation.items()
        }
    elif pydantic_typing.get_origin(return_annotation) is tuple:
        # TODO: should we also enter this for `Annotated[Tuple[...], ...]`?
        requires_multiple_artifacts = has_tuple_return(func)

        if requires_multiple_artifacts:
            output_signature = {}

            args = typing.get_args(return_annotation)
            if args[-1] is Ellipsis:
                raise RuntimeError(
                    "Variable length output annotations are not allowed."
                )

            for i, annotation in enumerate(args):
                resolved_annotation, output_name = resolve_type_annotation(
                    annotation
                )
                output_name = output_name or f"output_{i}"
                if output_name in output_signature:
                    raise RuntimeError(f"Duplicate output name {output_name}.")

                output_signature[output_name] = resolved_annotation

            return output_signature

    resolved_annotation, output_name = resolve_type_annotation(
        return_annotation
    )
    output_signature = {
        output_name or SINGLE_RETURN_OUT_NAME: resolved_annotation
    }

    return output_signature


def resolve_type_annotation(obj: Any) -> Tuple[Any, Optional[str]]:
    """Returns the non-generic class for generic aliases of the typing module.

    Example: if the input object is `typing.Dict`, this method will return the
    concrete class `dict`.

    Args:
        obj: The object to resolve.

    Returns:
        The non-generic class for generic aliases of the typing module and
        optional annotation metadata if it exists.
    """
    origin = pydantic_typing.get_origin(obj) or obj

    if origin is Annotated:
        annotation, *_ = typing.get_args(obj)
        output_name = validate_annotation_metadata(obj)

        resolved_annotation, _ = resolve_type_annotation(annotation)
        return resolved_annotation, output_name

    elif pydantic_typing.is_union(origin):
        return obj, None

    return origin, None


def validate_annotation_metadata(annotation: Any) -> str:
    """Validates annotation metadata.

    Args:
        annotation: The type annotation, must be of type `Annotated[...]`

    Raises:
        ValueError: If the annotation contains multiple metadata fields or a
            single non-string metadata field.

    Returns:
        The annotation metadata.
    """
    annotation, *metadata = typing.get_args(annotation)

    if len(metadata) != 1:
        raise ValueError(
            "Annotation metadata can only contain a single element which must "
            "be the output name."
        )

    output_name = metadata[0]

    if not isinstance(output_name, str):
        raise ValueError(
            "Annotation metadata must be a string which will be used as the "
            "output name."
        )

    return output_name


class ReturnVisitor(ast.NodeVisitor):
    """AST visitor class that can be subclasses to visit function returns."""

    def __init__(self, ignore_nested_functions: bool = True) -> None:
        """Initializes a return visitor instance.

        Args:
            ignore_nested_functions: If `True`, will skip visiting nested
            functions.
        """
        self._ignore_nested_functions = ignore_nested_functions
        self._inside_function = False

    def _visit_function(
        self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef]
    ) -> None:
        """Visit a (async) function defition node.

        Args:
            node: The node to visit.
        """
        if self._ignore_nested_functions and self._inside_function:
            # We're already inside a function definition and should ignore
            # nested functions so we don't want to recurse any further
            return

        self._inside_function = True
        self.generic_visit(node)

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function


class OnlyNoneReturnsVisitor(ReturnVisitor):
    """Checks whether a function AST contains only `None` returns."""

    def __init__(self) -> None:
        """Initializes a visitor instance."""
        super().__init__()
        self.has_only_none_returns = True

    def visit_Return(self, node: ast.Return) -> None:
        """Visit a return statement.

        Args:
            node: The return statement to visit.
        """
        if node.value is not None:
            if isinstance(node.value, (ast.Constant, ast.NameConstant)):
                if node.value.value is None:
                    return

            self.has_only_none_returns = False


class TupleReturnVisitor(ReturnVisitor):
    """Checks whether a function AST contains tuple returns."""

    def __init__(self) -> None:
        """Initializes a visitor instance."""
        super().__init__()
        self.has_tuple_return = False

    def visit_Return(self, node: ast.Return) -> None:
        """Visit a return statement.

        Args:
            node: The return statement to visit.
        """
        if isinstance(node.value, ast.Tuple) and len(node.value.elts) > 1:
            self.has_tuple_return = True


def has_tuple_return(func: Callable[..., Any]) -> bool:
    """Checks whether a function returns multiple values.

    Multiple values means that the `return` statement is followed by a tuple
    (with or without brackets).

    Example:
    ```
    def f1():
      return 1, 2

    def f2():
      return (1, 2)

    def f3():
      var = (1, 2)
      return var

    has_tuple_return(f1)  # True
    has_tuple_return(f2)  # True
    has_tuple_return(f3)  # False
    ```

    Args:
        func: The function to check.

    Returns:
        Whether the function returns multiple values.
    """
    source = textwrap.dedent(source_code_utils.get_source_code(func))
    tree = ast.parse(source)

    visitor = TupleReturnVisitor()
    visitor.visit(tree)

    return visitor.has_tuple_return


def has_only_none_returns(func: Callable[..., Any]) -> bool:
    """Checks whether a function contains only `None` returns.

    A `None` return could be either an explicit `return None` or an empty
    `return` statement.

    Args:
        func: The function to check.

    Returns:
        Whether the function contains only `None` returns.
    """
    source = textwrap.dedent(source_code_utils.get_source_code(func))
    tree = ast.parse(source)

    visitor = OnlyNoneReturnsVisitor()
    visitor.visit(tree)

    return visitor.has_only_none_returns
