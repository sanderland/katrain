import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardActionArea from '@mui/material/CardActionArea';
import CircularProgress from '@mui/material/CircularProgress';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import { TutorialAPI } from '../../api/tutorialApi';
import type { TutorialBook } from '../../../types/tutorial';

export default function TutorialBooksPage() {
  const { category } = useParams<{ category: string }>();
  const navigate = useNavigate();
  const [books, setBooks] = useState<TutorialBook[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    if (!category) return;
    setLoading(true);
    setError(null);
    TutorialAPI.getBooks(category)
      .then(setBooks)
      .catch(e => setError(e instanceof Error ? e.message : '加载失败'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [category]);

  if (loading) return <Box display="flex" justifyContent="center" p={4}><CircularProgress /></Box>;
  if (error) return <Box p={3}><Alert severity="error">{error} <Button onClick={load}>重试</Button></Alert></Box>;

  return (
    <Box p={3}>
      <Button size="small" onClick={() => navigate('/galaxy/tutorials')} sx={{ mb: 1 }}>← 返回</Button>
      <Typography variant="h5" gutterBottom>{category}</Typography>
      {books.length === 0 ? (
        <Typography color="text.secondary">该分类暂无书籍</Typography>
      ) : (
        <Box display="flex" flexWrap="wrap" gap={2} mt={1}>
          {books.map(book => (
            <Box key={book.id} sx={{ flex: '1 1 280px', maxWidth: 400 }}>
              <Card>
                <CardActionArea onClick={() => navigate(`/galaxy/tutorials/book/${book.id}`)}>
                  <CardContent>
                    <Typography variant="h6">{book.title}</Typography>
                    {book.author && <Typography variant="body2" color="text.secondary">{book.author}</Typography>}
                    <Typography variant="caption" color="text.secondary" mt={1} display="block">
                      {book.chapter_count} 章
                    </Typography>
                  </CardContent>
                </CardActionArea>
              </Card>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}
