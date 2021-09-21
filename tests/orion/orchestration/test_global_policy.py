import datetime
import pendulum
import pytest

from prefect.orion.orchestration.rules import TERMINAL_STATES
from prefect.orion.orchestration.global_policy import (
    UpdateRunDetails,
)
from prefect.orion.schemas import states


@pytest.mark.parametrize("run_type", ["task", "flow"])
class TestUpdateRunDetailsRule:
    @pytest.mark.parametrize("proposed_state_type", list(states.StateType))
    async def test_rule_updates_run_state(
        self, session, run_type, initialize_orchestration, proposed_state_type
    ):
        initial_state_type = None
        intended_transition = (initial_state_type, proposed_state_type)
        ctx = await initialize_orchestration(
            session,
            run_type,
            *intended_transition,
        )

        async with UpdateRunDetails(ctx, *intended_transition) as ctx:
            await ctx.validate_proposed_state()

        run = ctx.run
        assert run.state_type == proposed_state_type

    async def test_rule_sets_scheduled_time(
        self,
        session,
        run_type,
        initialize_orchestration,
    ):
        initial_state_type = None
        proposed_state_type = states.StateType.SCHEDULED
        intended_transition = (initial_state_type, proposed_state_type)
        scheduled_time = pendulum.now().add(seconds=42)
        ctx = await initialize_orchestration(
            session,
            run_type,
            *intended_transition,
            proposed_details={"scheduled_time": scheduled_time},
        )

        run = ctx.run
        assert run.start_time is None

        async with UpdateRunDetails(ctx, *intended_transition) as ctx:
            await ctx.validate_proposed_state()

        assert run.next_scheduled_start_time == scheduled_time
        assert run.expected_start_time == scheduled_time
        assert run.start_time is None

    async def test_rule_sets_expected_start_time(
        self,
        session,
        run_type,
        initialize_orchestration,
    ):
        initial_state_type = states.StateType.SCHEDULED
        proposed_state_type = states.StateType.PENDING
        intended_transition = (initial_state_type, proposed_state_type)
        ctx = await initialize_orchestration(
            session,
            run_type,
            *intended_transition,
        )

        run = ctx.run
        assert run.start_time is None

        async with UpdateRunDetails(ctx, *intended_transition) as ctx:
            await ctx.validate_proposed_state()

        assert run.expected_start_time is not None
        assert run.start_time is None

    async def test_rule_sets_start_time_when_starting_to_run(
        self,
        session,
        run_type,
        initialize_orchestration,
    ):
        initial_state_type = states.StateType.PENDING
        proposed_state_type = states.StateType.RUNNING
        intended_transition = (initial_state_type, proposed_state_type)
        ctx = await initialize_orchestration(
            session,
            run_type,
            *intended_transition,
        )

        run = ctx.run
        assert run.start_time is None

        async with UpdateRunDetails(ctx, *intended_transition) as ctx:
            await ctx.validate_proposed_state()

        assert run.start_time is not None

    async def test_rule_updates_run_count_when_starting_to_run(
        self,
        session,
        run_type,
        initialize_orchestration,
    ):
        initial_state_type = states.StateType.PENDING
        proposed_state_type = states.StateType.RUNNING
        intended_transition = (initial_state_type, proposed_state_type)
        ctx = await initialize_orchestration(
            session,
            run_type,
            *intended_transition,
        )

        run = ctx.run
        assert run.run_count == 0

        async with UpdateRunDetails(ctx, *intended_transition) as ctx:
            await ctx.validate_proposed_state()

        assert run.run_count == 1

    async def test_rule_increments_run_count(
        self,
        session,
        run_type,
        initialize_orchestration,
    ):
        initial_state_type = states.StateType.PENDING
        proposed_state_type = states.StateType.RUNNING
        intended_transition = (initial_state_type, proposed_state_type)
        ctx = await initialize_orchestration(
            session,
            run_type,
            *intended_transition,
        )

        run = ctx.run
        run.run_count = 41

        async with UpdateRunDetails(ctx, *intended_transition) as ctx:
            await ctx.validate_proposed_state()

        assert run.run_count == 42

    async def test_rule_updates_run_time_after_running(
        self,
        session,
        run_type,
        initialize_orchestration,
    ):
        initial_state_type = states.StateType.RUNNING
        proposed_state_type = states.StateType.COMPLETED
        intended_transition = (initial_state_type, proposed_state_type)
        ctx = await initialize_orchestration(
            session,
            run_type,
            *intended_transition,
        )

        now = pendulum.now()
        run = ctx.run
        run.start_time = now.subtract(seconds=42)
        ctx.initial_state.timestamp = now.subtract(seconds=42)
        ctx.proposed_state.timestamp = now
        await session.commit()
        assert run.total_run_time == datetime.timedelta(0)

        async with UpdateRunDetails(ctx, *intended_transition) as ctx:
            await ctx.validate_proposed_state()

        assert run.total_run_time == datetime.timedelta(seconds=42)

    async def test_rule_doesnt_update_run_time_when_not_running(
        self,
        session,
        run_type,
        initialize_orchestration,
    ):
        initial_state_type = states.StateType.PENDING
        proposed_state_type = states.StateType.COMPLETED
        intended_transition = (initial_state_type, proposed_state_type)
        ctx = await initialize_orchestration(
            session,
            run_type,
            *intended_transition,
        )

        now = pendulum.now()
        run = ctx.run
        run.start_time = now.subtract(seconds=42)
        ctx.initial_state.timestamp = now.subtract(seconds=42)
        ctx.proposed_state.timestamp = now
        await session.commit()
        await session.refresh(run)
        assert run.total_run_time == datetime.timedelta(0)

        async with UpdateRunDetails(ctx, *intended_transition) as ctx:
            await ctx.validate_proposed_state()

        assert run.total_run_time == datetime.timedelta(0)

    @pytest.mark.parametrize("proposed_state_type", TERMINAL_STATES)
    async def test_rule_sets_end_time_when_when_run_ends(
        self, session, run_type, initialize_orchestration, proposed_state_type
    ):
        initial_state_type = states.StateType.RUNNING
        intended_transition = (initial_state_type, proposed_state_type)
        ctx = await initialize_orchestration(
            session,
            run_type,
            *intended_transition,
        )

        run = ctx.run
        run.start_time = pendulum.now().subtract(seconds=42)
        assert run.end_time is None

        async with UpdateRunDetails(ctx, *intended_transition) as ctx:
            await ctx.validate_proposed_state()

        assert run.end_time is not None

    @pytest.mark.parametrize("initial_state_type", TERMINAL_STATES)
    async def test_rule_unsets_end_time_when_forced_out_of_terminal_state(
        self, session, run_type, initialize_orchestration, initial_state_type
    ):
        proposed_state_type = states.StateType.RUNNING
        intended_transition = (initial_state_type, proposed_state_type)
        ctx = await initialize_orchestration(
            session,
            run_type,
            *intended_transition,
        )

        run = ctx.run
        run.start_time = pendulum.now().subtract(seconds=42)
        run.end_time = pendulum.now()
        assert run.end_time is not None

        async with UpdateRunDetails(ctx, *intended_transition) as ctx:
            await ctx.validate_proposed_state()

        assert run.end_time is None
