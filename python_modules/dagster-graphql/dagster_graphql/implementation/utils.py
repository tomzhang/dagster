import sys
from collections import namedtuple

from dagster import check
from dagster.core.host_representation import PipelineSelector
from dagster.utils.error import serializable_error_info_from_exc_info


def capture_dauphin_error(fn):
    def _fn(*args, **kwargs):
        from dagster_graphql.schema.errors import DauphinPythonError

        try:
            return fn(*args, **kwargs)
        except UserFacingGraphQLError as de_exception:
            return de_exception.dauphin_error
        except Exception:  # pylint: disable=broad-except
            return DauphinPythonError(serializable_error_info_from_exc_info(sys.exc_info()))

    return _fn


class UserFacingGraphQLError(Exception):
    def __init__(self, dauphin_error):
        self.dauphin_error = dauphin_error
        message = '[{cls}] {message}'.format(
            cls=dauphin_error.__class__.__name__,
            message=dauphin_error.message if hasattr(dauphin_error, 'message') else None,
        )
        super(UserFacingGraphQLError, self).__init__(message)


def legacy_pipeline_selector(context, name, solid_selection):
    from dagster_graphql.implementation.context import DagsterGraphQLContext

    check.inst_param(context, 'context', DagsterGraphQLContext)

    return PipelineSelector(
        location_name=context.legacy_location.name,
        repository_name=context.legacy_external_repository.name,
        pipeline_name=name,
        solid_selection=solid_selection,
    )


def pipeline_selector_from_graphql(context, data):
    from dagster_graphql.implementation.context import DagsterGraphQLContext

    check.inst_param(context, 'context', DagsterGraphQLContext)

    # legacy case
    if data.get('name'):
        check.invariant(
            data.get('repositoryLocationName') is None
            and data.get('repositoryName') is None
            and data.get('pipelineName') is None,
            'Invalid legacy PipelineSelector, contains modern name fields',
        )

        return legacy_pipeline_selector(
            context, name=data['name'], solid_selection=data.get('solidSelection'),
        )

    # can be removed once DauphinPipelineSelector fields
    # can be made NonNull
    check.invariant(
        data.get('repositoryLocationName')
        and data.get('repositoryName')
        and data.get('pipelineName'),
        'Invalid PipelineSelector, must have all name fields',
    )

    return PipelineSelector(
        location_name=data['repositoryLocationName'],
        repository_name=data['repositoryName'],
        pipeline_name=data['pipelineName'],
        solid_selection=data.get('solidSelection'),
    )


class ExecutionParams(
    namedtuple('_ExecutionParams', 'selector environment_dict mode execution_metadata step_keys',)
):
    def __new__(cls, selector, environment_dict, mode, execution_metadata, step_keys):
        check.dict_param(environment_dict, 'environment_dict', key_type=str)
        check.opt_list_param(step_keys, 'step_keys', of_type=str)

        return super(ExecutionParams, cls).__new__(
            cls,
            selector=check.inst_param(selector, 'selector', PipelineSelector),
            environment_dict=environment_dict,
            mode=check.str_param(mode, 'mode'),
            execution_metadata=check.inst_param(
                execution_metadata, 'execution_metadata', ExecutionMetadata
            ),
            step_keys=step_keys,
        )

    def to_graphql_input(self):
        return {
            'selector': self.selector.to_graphql_input(),
            'runConfigData': self.environment_dict,
            'mode': self.mode,
            'executionMetadata': self.execution_metadata.to_graphql_input(),
            'stepKeys': self.step_keys,
        }


class ExecutionMetadata(namedtuple('_ExecutionMetadata', 'run_id tags root_run_id parent_run_id')):
    def __new__(cls, run_id, tags, root_run_id=None, parent_run_id=None):
        return super(ExecutionMetadata, cls).__new__(
            cls,
            check.opt_str_param(run_id, 'run_id'),
            check.dict_param(tags, 'tags', key_type=str, value_type=str),
            check.opt_str_param(root_run_id, 'root_run_id'),
            check.opt_str_param(parent_run_id, 'parent_run_id'),
        )

    def to_graphql_input(self):
        return {
            'runId': self.run_id,
            'tags': [{'key': k, 'value': v} for k, v in self.tags.items()],
            'rootRunId': self.root_run_id,
            'parentRunId': self.parent_run_id,
        }
