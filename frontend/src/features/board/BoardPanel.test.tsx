import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ChesspulseApi } from '../../services/chesspulseApi';
import * as fx from '../../test/fixtures';
import { BoardPanel } from './BoardPanel';
import { START_FEN } from './position';

afterEach(cleanup);

function fakeApi(): ChesspulseApi {
  return {
    boardEvaluate: vi.fn().mockResolvedValue(fx.boardEvaluation),
    boardMove: vi.fn().mockResolvedValue(fx.boardMove),
  } as unknown as ChesspulseApi;
}

describe('free board', () => {
  it('evaluates the current position and shows the engine suggestion', async () => {
    const api = fakeApi();
    render(<BoardPanel api={api} />);

    fireEvent.click(screen.getByRole('button', { name: 'Evaluate position' }));

    expect(await screen.findByText('+0.35')).toBeTruthy();
    expect(screen.getByText('e4')).toBeTruthy();
    expect(api.boardEvaluate).toHaveBeenCalledWith(START_FEN);
  });

  it('plays a legal move and classifies it', async () => {
    const api = fakeApi();
    render(<BoardPanel api={api} />);

    fireEvent.click(screen.getByRole('button', { name: 'e2 white pawn' }));
    fireEvent.click(screen.getByRole('button', { name: 'e4' }));

    await waitFor(() => expect(api.boardMove).toHaveBeenCalledWith(START_FEN, 'e2e4'));
    expect(await screen.findByText('Best')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'e4 white pawn' })).toBeTruthy();
    expect((screen.getByLabelText('Position FEN') as HTMLInputElement).value).toContain('4P3');
  });

  it('edits arbitrary positions and explains an invalid setup', async () => {
    render(<BoardPanel api={fakeApi()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Clear board' }));
    expect(screen.getByText('Editing')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'White king' }));
    fireEvent.click(screen.getByRole('button', { name: 'e1' }));
    expect((screen.getByLabelText('Position FEN') as HTMLInputElement).value).toContain('/4K3');

    fireEvent.click(screen.getByRole('button', { name: 'Play this position' }));
    expect((await screen.findByRole('alert')).textContent).toMatch(/king/i);

    fireEvent.click(screen.getByRole('button', { name: 'Black king' }));
    fireEvent.click(screen.getByRole('button', { name: 'e8' }));
    fireEvent.click(screen.getByRole('button', { name: 'Play this position' }));

    expect(screen.getByText('Playing')).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('plays the engine suggestion with one click', async () => {
    const api = fakeApi();
    render(<BoardPanel api={api} />);

    fireEvent.click(screen.getByRole('button', { name: 'Evaluate position' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Play it' }));

    await waitFor(() => expect(api.boardMove).toHaveBeenCalledWith(START_FEN, 'e2e4'));
  });
});
