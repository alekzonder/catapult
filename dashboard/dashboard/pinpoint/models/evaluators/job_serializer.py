# Copyright 2019 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from dashboard.pinpoint.models import change as change_module
from dashboard.pinpoint.models import evaluators
from dashboard.pinpoint.models.tasks import find_isolate
from dashboard.pinpoint.models.tasks import performance_bisection
from dashboard.pinpoint.models.tasks import read_value
from dashboard.pinpoint.models.tasks import run_test


class Serializer(evaluators.DispatchByTaskType):
  """Serializes a task graph associated with a job.

  This Serializer follows the same API contract of an Evaluator, which applies
  specific transformations based on the type of a task in the graph.

  The end state of the context argument is a mapping with the following schema:

    {
      'comparison_mode': <string>
      'metric': <string>
      'quests': [<string>]
      'state': [
        {
          'attempts': [
            {
              'executions': [
                {
                  'completed': <boolean>
                  'exception': <string>
                  'details': [
                    {
                      'key': <string>
                      'value': <string>
                      'url': <string>
                    }
                  ]
                }
              ]
            }
          ]
          'change': { ... }
          'comparisons': {
            'next': <string|None>
            'prev': <string|None>
          }
          'result_values': [
            <float>
          ]
        }
      ]
    }

  NOTE: The 'quests' and 'executions' in the schema are legacy names, which
  refers to the previous quest abstractions from which the tasks and evaluators
  are derived from. We keep the name in the schema to ensure that we are
  backwards-compatible with what the consumers of the data expect (i.e. the Web
  UI).
  """

  def __init__(self):
    super(Serializer, self).__init__({
        'find_isolate':
            evaluators.SequenceEvaluator(
                [find_isolate.Serializer(), TaskTransformer]),
        'run_test':
            evaluators.SequenceEvaluator(
                [run_test.Serializer(), TaskTransformer]),
        'read_value':
            evaluators.SequenceEvaluator(
                [read_value.Serializer(), TaskTransformer]),
        'find_culprit':
            evaluators.SequenceEvaluator(
                [performance_bisection.Serializer(), AnalysisTransformer]),
    })

  def __call__(self, task, event, context):
    # First we delegate to the task-specific serializers, and have the
    # domain-aware transformers canonicalise the data in the context. We
    # then do a dictionary merge following a simple protocol for editing a
    # single context. This way the transformers can output a canonical set
    # of transformations to build up the (global) context.
    local_context = {}
    super(Serializer, self).__call__(task, event, local_context)

    # What we expect to see in the local context is data in the following
    # form:
    #
    #   {
    #      # The 'state' key is required to identify to which change and which
    #      # state we should be performing the actions.
    #      'state': {
    #         'change': {...}
    #         'quest': <string>
    #
    #         # In the quest-based system, we end up with different "execution"
    #         # details, which come in "quest" order. In the task-based
    #         # evaluation model, the we use the 'index' in the 'add_details'
    #         # sub-object to identify the index in the details.
    #         'add_execution': {
    #             'add_details': {
    #                 'index': <int>
    #                 ...
    #             }
    #             ...
    #         }
    #
    #         # This allows us to accumulate the resulting values we encounter
    #         # associated with the change.
    #         'append_result_values': [<float>]
    #
    #         # This allows us to set the comparison result for this change in
    #         # context of other changes.
    #         'set_comparison': {
    #             'next': <string|None>,
    #             'prev': <string|None>,
    #         }
    #      }
    #
    #      # If we see the 'order_changes' key in the local context, then
    #      # that means we can sort the states according to the changes as they
    #      # appear in this list.
    #      'order_changes': [...]
    #
    #      # If we see the 'set_parameters' key in the local context, then
    #      # we can set the overall parameters we're looking to compare and
    #      # convey in the results.
    #      'set_parameters': {
    #          'comparison_mode': <string>
    #          'metric': <string>
    #      }
    #   }
    #
    # At this point we process the context to update the global context
    # following the protocol defined above.
    if 'state' in local_context:
      modification = local_context['state']
      states = context.setdefault('state', [])
      quests = context.setdefault('quests', [])

      # We need to find the existing state which matches the quest and the
      # change. If we don't find one, we create the first state entry for that.
      state_index = None
      change = modification.get('change')
      for index, state in enumerate(states):
        if state.get('change') == change:
          state_index = index
          break

      if state_index is None:
        states.append({'attempts': [{'executions': []}], 'change': change})
        state_index = len(states) - 1

      quest = modification.get('quest')
      try:
        quest_index = quests.index(quest)
      except ValueError:
        quests.append(quest)
        quest_index = len(quests) - 1

      add_execution = modification.get('add_execution')
      append_result_values = modification.get('append_result_values')
      attempt_index = modification.get('index', 0)
      set_comparison = modification.get('set_comparison')
      state = states[state_index]
      if add_execution:
        attempts = state['attempts']
        while len(attempts) < attempt_index + 1:
          attempts.append({'executions': []})
        executions = state['attempts'][attempt_index]['executions']
        while len(executions) < quest_index + 1:
          executions.append(None)
        executions[quest_index] = dict(add_execution)

      if append_result_values:
        state.setdefault('result_values', []).extend(append_result_values)

      if set_comparison:
        state.setdefault('comparisons', {}).update(set_comparison)

    if 'order_changes' in local_context:
      # Here, we'll sort the states according to their order of appearance in
      # the 'order_changes' list.
      order_changes = local_context.get('order_changes')
      change_index = {
          change: index for index, change in enumerate(order_changes)
      }
      states = context.get('state')
      assert len(order_changes) == len(states)
      if states:
        ordered_states = [None] * len(states)
        for state in states:
          ordered_states[change_index[change_module.Change.FromDict(
              state.get('change'))]] = state
        context['state'] = ordered_states

    if 'set_parameters' in local_context:
      modification = local_context.get('set_parameters')
      context['comparison_mode'] = modification.get('comparison_mode')
      context['metric'] = modification.get('metric')


TASK_TYPE_QUEST_MAPPING = {
    'find_isolate': 'Build',
    'run_test': 'Test',
    'read_value': 'Get results',
}


def TaskTransformer(task, _, context):
  """Takes the form:

  {
    <task id> : {
      ...
    }
  }

  And turns it into:

  {
    'state': {
      'change': {...}
      'quest': <string>
      'index': <int>
      'add_execution': {
        ...
      }
    }
  }
  """
  input_data = context.get(task.id)
  if not input_data:
    return None

  result = {
      'state': {
          'change': task.payload.get('change'),
          'quest': TASK_TYPE_QUEST_MAPPING.get(task.task_type),
          'index': task.payload.get('index', 0),
          'add_execution': input_data,
      }
  }
  context.clear()
  context.update(result)


def AnalysisTransformer(task, _, context):
  """Takes the form:

  {
    <task id> : {
      ...
    }
  }

  And turns it into:

  {
    'set_parameters': {
      'comparison_mode': ...
      'metric': ...
    }
    'order_changes': [
      <change>, ...
    ]
  }
  """
  task_data = context.get(task.id)
  result = {
      'set_parameters': {
          'comparison_mode': task_data.get('comparison_mode'),
          'metric': task_data.get('metric'),
      },
      'order_changes': task_data.get('changes')
  }
  context.clear()
  context.update(result)
